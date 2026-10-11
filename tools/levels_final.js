const fs = require('fs');
const buf = fs.readFileSync('Bumpy (1989)(Loriciels).z80');
const data = buf.subarray(32); // skip 32-byte Z80 header
const out = [];

function hex(n, w=4) { return '0x' + n.toString(16).toUpperCase().padStart(w,'0'); }

function dumpRegion(start, len, label) {
  out.push(`\n--- ${label} (${hex(start)}, len=${len}) ---`);
  for (let i = start; i < start + len && i < data.length; i += 16) {
    let hexStr = '', asc = '';
    for (let j = 0; j < 16 && i+j < data.length; j++) {
      const b = data[i+j];
      hexStr += b.toString(16).padStart(2,'0') + ' ';
      asc += (b >= 32 && b < 127) ? String.fromCharCode(b) : '.';
    }
    out.push(`  ${hex(i)}  ${hexStr.padEnd(48)} |${asc}|`);
  }
}

function grid(offset, w=6, h=6) {
  if (offset + w*h > data.length) return null;
  const rows = [];
  for (let r = 0; r < h; r++) {
    const row = [];
    for (let c = 0; c < w; c++) row.push(data[offset + r*w + c]);
    rows.push(row);
  }
  return rows;
}

function fmtGrid(rows) {
  if (!rows) return '  (out of bounds)';
  const lines = [];
  for (const row of rows) {
    lines.push('  ' + row.map(v => String(v).padStart(2)).join('  '));
  }
  return lines.join('\n');
}

// === 1. STRICT SCAN: 36-byte blocks, max<=4, zeros>=12 ===
out.push('=== STRICT LEVEL SCAN (max<=4, zeros>=12) ===');
const strict = [];
for (let i = 0; i + 36 <= data.length; i++) {
  let mx = 0, zeros = 0;
  for (let j = 0; j < 36; j++) {
    const v = data[i+j];
    if (v > mx) mx = v;
    if (v === 0) zeros++;
  }
  if (mx <= 4 && zeros >= 12) strict.push({off: i, mx, zeros});
}
// Group consecutive/nearby candidates (within 36 bytes of each other)
const groups = [];
for (const c of strict) {
  const last = groups[groups.length-1];
  if (last && c.off - last[last.length-1].off < 40) {
    last.push(c);
  } else {
    groups.push([c]);
  }
}
out.push(`Found ${strict.length} strict candidates in ${groups.length} groups:`);
for (const g of groups) {
  const first = g[0], last = g[g.length-1];
  out.push(`  Group at ${hex(first.off)}-${hex(last.off+36)} (${g.length} overlapping candidates, span=${last.off-first.off+36} bytes)`);
  // Show the "best" candidate in the group (most zeros)
  let best = g[0];
  for (const c of g) if (c.zeros > best.zeros) best = c;
  out.push(`  Best: ${hex(best.off)} max=${best.mx} zeros=${best.zeros}`);
  const rows = grid(best.off);
  out.push(fmtGrid(rows));
}

// === 2. MEDIUM SCAN: 36-byte blocks, max<=8, zeros>=10 ===
out.push('\n=== MEDIUM LEVEL SCAN (max<=8, zeros>=10) ===');
const med = [];
for (let i = 0; i + 36 <= data.length; i++) {
  let mx = 0, zeros = 0;
  for (let j = 0; j < 36; j++) {
    const v = data[i+j];
    if (v > mx) mx = v;
    if (v === 0) zeros++;
  }
  if (mx <= 8 && zeros >= 10) med.push({off: i, mx, zeros});
}
const medGroups = [];
for (const c of med) {
  const last = medGroups[medGroups.length-1];
  if (last && c.off - last[last.length-1].off < 40) {
    last.push(c);
  } else {
    medGroups.push([c]);
  }
}
out.push(`Found ${med.length} medium candidates in ${medGroups.length} groups:`);
for (const g of medGroups) {
  const first = g[0], last = g[g.length-1];
  let best = g[0];
  for (const c of g) if (c.zeros > best.zeros) best = c;
  out.push(`  Group ${hex(first.off)}-${hex(last.off+36)}: best=${hex(best.off)} max=${best.mx} zeros=${best.zeros}`);
  const rows = grid(best.off);
  out.push(fmtGrid(rows));
}

// === 3. LOOK FOR CONSECUTIVE NON-OVERLAPPING 36-BYTE LEVELS ===
out.push('\n=== CONSECUTIVE LEVEL BLOCKS (non-overlapping, max<=8) ===');
// Try to find sequences of N consecutive 36-byte blocks that all look like levels
for (let start = 0; start + 72 <= data.length; start++) {
  // Check if two consecutive 36-byte blocks both look like levels
  let ok = true;
  for (let b = 0; b < 2 && ok; b++) {
    const off = start + b*36;
    let mx = 0, zeros = 0;
    for (let j = 0; j < 36; j++) {
      const v = data[off+j];
      if (v > mx) mx = v;
      if (v === 0) zeros++;
    }
    if (mx > 8 || zeros < 10) ok = false;
  }
  if (ok) {
    out.push(`  Pair at ${hex(start)}: `);
    for (let b = 0; b < 2; b++) {
      const off = start + b*36;
      const rows = grid(off);
      out.push(`  Level ${b}:`);
      out.push(fmtGrid(rows));
    }
  }
}

// === 4. DUMP KEY REGIONS ===
dumpRegion(0x0F80, 128, 'REGION 0x0F80 (before/around level candidate)');
dumpRegion(0x0FF0, 64, 'REGION 0x0FF0 (after level candidate)');
dumpRegion(0x0F00, 96, 'REGION 0x0F00 (wider context)');

// === 5. LOOK FOR LEVEL COUNT / INDEX TABLES ===
out.push('\n=== SEARCH FOR LEVEL COUNT BYTES ===');
// Look for a byte followed by N * 36 or N * 72 pattern
for (let i = 0; i < data.length - 4; i++) {
  const n = data[i];
  if (n >= 1 && n <= 20) {
    // Check if next bytes could be a table of offsets (each 2 bytes, little-endian)
    let valid = true;
    for (let j = 0; j < n; j++) {
      const off = i + 1 + j*2;
      if (off + 1 >= data.length) { valid = false; break; }
      const addr = data[off] | (data[off+1] << 8);
      if (addr > 0xBFFF) valid = false;
    }
    if (valid && n >= 2 && n <= 10) {
      // Additional check: the offsets should be in increasing order and point to plausible data
      let increasing = true;
      let prev = 0;
      for (let j = 0; j < n; j++) {
        const off = i + 1 + j*2;
        const addr = data[off] | (data[off+1] << 8);
        if (addr < prev) increasing = false;
        prev = addr;
      }
      if (increasing) {
        out.push(`  Possible level table at ${hex(i)}: count=${n}`);
        for (let j = 0; j < n; j++) {
          const off = i + 1 + j*2;
          const addr = data[off] | (data[off+1] << 8);
          out.push(`    Level ${j}: offset=${hex(addr)}`);
        }
      }
    }
  }
}

// === 6. CHECK SPECIFIC AREAS FOR MORE LEVELS ===
// Look at areas that had medium candidates
const interestingAreas = [0x1300, 0x1590, 0x1A80, 0x2030, 0x22B0];
for (const area of interestingAreas) {
  dumpRegion(area, 64, `INTERESTING AREA ${hex(area)}`);
}

// === 7. FULL DUMP OF 0x0FD0-0x1020 (the main candidate region + surroundings) ===
dumpRegion(0x0FC0, 96, 'FULL DUMP 0x0FC0-0x1020');

// === 8. LOOK FOR REPEATED GRID PATTERNS (same level used twice?) ===
out.push('\n=== REPEATED 36-BYTE BLOCKS (exact matches) ===');
const blockMap = new Map();
for (let i = 0; i + 36 <= data.length; i++) {
  const key = Buffer.from(data.subarray(i, i+36)).toString('hex');
  if (!blockMap.has(key)) blockMap.set(key, []);
  blockMap.get(key).push(i);
}
let repCount = 0;
for (const [key, offsets] of blockMap) {
  if (offsets.length >= 2) {
    // Check if this block looks like a level (small values)
    let mx = 0;
    for (let j = 0; j < 36; j++) if (data[offsets[0]+j] > mx) mx = data[offsets[0]+j];
    if (mx <= 8) {
      repCount++;
      out.push(`  Repeated block (max=${mx}) at: ${offsets.map(hex).join(', ')}`);
      const rows = grid(offsets[0]);
      out.push(fmtGrid(rows));
    }
  }
}
if (repCount === 0) out.push('  No repeated level-like blocks found.');

// Write output
const text = out.join('\n');
fs.writeFileSync('tools/z80_final.txt', text);
console.log(`Analysis written to tools/z80_final.txt (${text.split('\n').length} lines)`);
