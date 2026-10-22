#!/usr/bin/env python3
"""Extract level metadata from the original ZX Spectrum game BUMPY.TAP.

The original game stores 100 levels as fixed 75-byte records in the CODE
block (BUMPY.CDE, loaded at 0x61A8 / 25000) starting at address 35825.
See origin/LEVELS.md for the reconstructed format.

Usage:
    python3 tools/extract_levels.py [path/to/BUMPY.TAP] [-o levels.json]
    python3 tools/extract_levels.py --text
"""

import argparse
import json
import os
import sys

DEFAULT_TAP = os.path.join(
    os.path.dirname(__file__), "..", "origin", "Bumpy.tap (1)", "BUMPY.TAP"
)
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "main", "levels.json")

CODE_BASE = 25000          # RANDOMIZE USR target / LOAD "" CODE 25000
LEVEL_TABLE = 35825        # LD HL,35825 in the loader at 53097
LEVEL_STRIDE = 75
LEVEL_FIRST_RECORD = 1     # level index 0 (43776) -> record (index + 1)
LEVEL_COUNT = 100
THEME_TABLE = 57625        # level % 7 + 1 -> 3 bytes (colors), stride 3
THEME_COUNT = 7
GRID_W = 6
GRID_H = 6
GRID_CELLS = GRID_W * GRID_H


def parse_tap(data):
    """Yield (header, body) for each header/data block pair in a TAP file."""
    off = 0
    blocks = []
    while off + 2 <= len(data):
        length = data[off] | (data[off + 1] << 8)
        block = data[off + 2:off + 2 + length]
        blocks.append(block)
        off += length + 2
    i = 0
    while i < len(blocks) - 1:
        header = blocks[i]
        body = blocks[i + 1]
        if header and header[0] == 0x00:
            name = header[2:12].decode("latin-1").rstrip()
            btype = header[1]
            dlen = header[12] | (header[13] << 8)
            param1 = header[14] | (header[15] << 8)
            yield {
                "name": name,
                "type": btype,
                "length": dlen,
                "load": param1,
                "body": body,
            }
            i += 2
        else:
            i += 1


def load_code(tap_data):
    for blk in parse_tap(tap_data):
        if blk["type"] == 3 and blk["name"].endswith(".CDE"):
            payload = blk["body"]
            assert payload[0] == 0xFF, "unexpected data block flag"
            return payload[1:1 + blk["length"]], blk
    raise SystemExit("BUMPY.CDE code block not found in TAP")


def read_record(code, index):
    start = LEVEL_TABLE + LEVEL_STRIDE * index
    return code[start - CODE_BASE:start - CODE_BASE + LEVEL_STRIDE]


def unpack(record):
    """Split a raw 75-byte record into structured level data."""
    lo = [[0] * GRID_W for _ in range(GRID_H)]
    hi = [[0] * GRID_W for _ in range(GRID_H)]
    for k in range(GRID_CELLS):
        byte = record[k]
        r, c = divmod(k, GRID_W)
        lo[r][c] = byte & 0x0F
        hi[r][c] = (byte >> 4) & 0x0F
    objects = [[0] * GRID_W for _ in range(GRID_H)]
    for k in range(GRID_CELLS):
        r, c = divmod(k, GRID_W)
        objects[r][c] = record[39 + k]
    return {
        "grid_lo": lo,
        "grid_hi": hi,
        "objects": objects,
        "raw_grid": list(record[:GRID_CELLS]),
        "start_cell": record[36],
        "timer": record[37],
        "timer_cell": record[38],
    }


def histogram(levels, key):
    counts = {}
    for lvl in levels:
        flat = [v for row in lvl[key] for v in row]
        for v in flat:
            counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items()))


def extract(tap_path):
    with open(tap_path, "rb") as fh:
        data = fh.read()
    code, blk = load_code(data)
    themes = {}
    for t in range(1, THEME_COUNT + 1):
        off = THEME_TABLE + 3 * t - CODE_BASE
        themes[str(t)] = list(code[off:off + 3])
    levels = []
    for n in range(LEVEL_COUNT):
        record = read_record(code, LEVEL_FIRST_RECORD + n)
        entry = {"level": n + 1}
        entry.update(unpack(record))
        entry["theme"] = (n % 7) + 1
        levels.append(entry)
    return {
        "game": "Bumpy",
        "source": os.path.relpath(tap_path),
        "code": {"name": blk["name"], "load": blk["load"], "length": blk["length"]},
        "level_count": LEVEL_COUNT,
        "grid": {"rows": GRID_H, "cols": GRID_W, "index": "row*6+col"},
        "level_table": {
            "address": LEVEL_TABLE,
            "stride": LEVEL_STRIDE,
            "first_record": LEVEL_FIRST_RECORD,
        },
        "theme_table": {
            "address": THEME_TABLE,
            "stride": 3,
            "colors": themes,
        },
        "record_layout": {
            "grid_bytes": [0, 36],
            "grid_packing": "low nibble -> grid_lo, high nibble -> grid_hi",
            "start_cell": 36,
            "timer": 37,
            "timer_cell": 38,
            "objects": [39, 75],
        },
        "type_histograms": {
            "grid_lo": histogram(levels, "grid_lo"),
            "grid_hi": histogram(levels, "grid_hi"),
            "objects": histogram(levels, "objects"),
        },
        "levels": levels,
    }


def print_text(model):
    print(f"{model['level_count']} levels, table @ {model['level_table']['address']}")
    print("type histograms:",
          json.dumps(model["type_histograms"], ensure_ascii=False))
    for lvl in model["levels"]:
        print(f"\n=== Level {lvl['level']} (theme {lvl['theme']}) "
              f"start_cell={lvl['start_cell']} timer={lvl['timer']} "
              f"timer_cell={lvl['timer_cell']} ===")
        for name, key in (("lo", "grid_lo"), ("hi", "grid_hi"),
                          ("obj", "objects")):
            print(f"  {name}:")
            for row in lvl[key]:
                print("    " + " ".join(f"{v:2d}" for v in row))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tap", nargs="?", default=DEFAULT_TAP,
                    help="path to BUMPY.TAP")
    ap.add_argument("-o", "--output", default=None,
                    help="write JSON here (default: main/levels.json)")
    ap.add_argument("--text", action="store_true",
                    help="print a human readable dump instead of JSON")
    args = ap.parse_args()

    model = extract(args.tap)
    if args.text:
        print_text(model)
        return
    out = args.output
    if out is None:
        out = DEFAULT_OUTPUT
    with open(out, "w") as fh:
        json.dump(model, fh, indent=1)
        fh.write("\n")
    print(f"wrote {out} ({model['level_count']} levels)")


if __name__ == "__main__":
    main()
