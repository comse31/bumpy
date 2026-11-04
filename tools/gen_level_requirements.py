#!/usr/bin/env python3
"""Генерирует main/level_requirements.json — минимальный стартовый набор
предметов для каждого уровня (пункт 19 плана).

Для каждого уровня решатель (tools/solve_level.py) ищет план прохождения с
лексикографической целью: (1) минимум предметов на старте, (2) максимум
подобранного по пути, (3) минимум действий. В файл попадают:

  drops   — сколько капель нужно иметь на старте уровня,
  keys    — сколько ключей,
  hammers — сколько молотков,
  status  — "solvable" (план найден) или "impossible" (пройти нельзя),
  optimal — доказана ли минимальность набора,
  used    — сколько каждого предмета реально тратится по плану.

Игра читает этот файл на старте уровня: если в кармане не хватает хотя бы
одного предмета, уровень заведомо непроходим — показывается плашка и игра
завершается (см. main/level/level_requirements.lua).

Использование:
    python3 tools/gen_level_requirements.py
    python3 tools/gen_level_requirements.py --out main/level_requirements.json
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import solve_level as sv  # noqa: E402

DEFAULT_LEVELS = os.path.join(HERE, "..", "main", "levels.json")
DEFAULT_OUT = os.path.join(HERE, "..", "main", "level_requirements.json")
RESOURCES = ("drop", "key", "hammer")


def requirements_for(level, node_cap):
    res = sv.solve(level, node_cap=node_cap)
    req = res.get("required", (0, 0, 0))
    used = res.get("used", (0, 0, 0))
    return {
        "drops": int(req[0]),
        "keys": int(req[1]),
        "hammers": int(req[2]),
        "used": {
            "drops": int(used[0]),
            "keys": int(used[1]),
            "hammers": int(used[2]),
        },
        "status": res["status"],
        "optimal": bool(res.get("optimal", False)),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Генерирует минимальные требования по предметам для уровней.")
    ap.add_argument("levels", nargs="?", default=DEFAULT_LEVELS,
                    help="путь к levels.json (по умолчанию main/levels.json)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="путь к результату (main/level_requirements.json)")
    ap.add_argument("--node-cap", type=int, default=300000,
                    help="лимит узлов поиска на уровень")
    args = ap.parse_args()

    with open(args.levels, encoding="utf-8") as fh:
        model = json.load(fh)

    out = {}
    stats = {"solvable": 0, "impossible": 0, "proven": 0}
    for data in model["levels"]:
        level = sv.Level(data)
        item = requirements_for(level, args.node_cap)
        out[str(level.index)] = item
        stats[item["status"]] = stats.get(item["status"], 0) + 1
        if item["optimal"]:
            stats["proven"] += 1
        req_txt = " ".join(
            f"{v} {name}" for v, name in zip(
                (item["drops"], item["keys"], item["hammers"]), RESOURCES) if v)
        print(f"L{level.index:>3} {item['status']:<10} "
              f"start=[{req_txt or 'none'}]")

    payload = {
        "version": 1,
        "source": "tools/gen_level_requirements.py",
        "note": ("Минимальный набор предметов на старте уровня. Если в кармане "
                 "меньше — уровень непроходим, игра завершается."),
        "levels": out,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print()
    print(f"записано: {args.out}")
    print(f"уровней: {len(out)}, solvable: {stats['solvable']}, "
          f"impossible: {stats['impossible']}, "
          f"минимальность доказана: {stats['proven']}")


if __name__ == "__main__":
    main()
