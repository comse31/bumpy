const fs = require('fs');
const path = require('path');
const out = [];
const log = (...a) => out.push(a.join(' '));

const d = fs.readFileSync(path.join(__dirname, '..', 'Bumpy (1989)(Loriciels).z80'));
const mem = d.slice(32); // memory after 32-byte header
log('=== LEVEL MATRIX SEARCH ===');
log('Memory size:', mem.length, '(0x' + mem.length.toString(16) + ')');

// PC from header
const pc = d.readUInt16LE(9);
log('PC: 0x' + pc.toString(16));

// Dump around PC
log('\n--- DUMP AROUND PC=0x' + pc.toString(16) + ' ---');
const pcStart = Math.max(0, pc - 16);
for (let row = 0; row < 8; row++) {
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const off = pcStart + row * 16 + c;
        if (off >= mem.length) break;
        const b = mem[off];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + (pcStart + row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

// Strategy: Look for blocks of 36 bytes where values are in a small range (0-15 or 0-31)
// This would suggest a 6x6 grid with cell types
log('\n--- SEARCH FOR 36-BYTE BLOCKS WITH LIMITED VALUE RANGE ---');

function analyzeBlock(start, len) {
    const block = mem.slice(start, start + len);
    let min = 255, max = 0;
    for (const b of block) {
        if (b < min) min = b;
        if (b > max) max = b;
    }
    return { min, max, range: max - min };
}

// Search for 36-byte blocks where all values are <= 15 (4-bit cell types)
log('\n--- 36-byte blocks with all values <= 15 ---');
let candidates15 = [];
for (let i = 0; i + 36 <= mem.length; i++) {
    let ok = true;
    for (let j = 0; j < 36; j++) {
        if (mem[i + j] > 15) { ok = false; break; }
    }
    if (ok) candidates15.push(i);
}
log('Found ' + candidates15.length + ' candidates');
// Show first 20
for (const off of candidates15.slice(0, 20)) {
    const hex = mem.slice(off, off + 36).map(b => b.toString(16).padStart(2, '0')).join(' ');
    log('  offset 0x' + off.toString(16).padStart(4, '0') + ': ' + hex);
}

// Search for 36-byte blocks where all values are <= 31 (5-bit cell types)
log('\n--- 36-byte blocks with all values <= 31 ---');
let candidates31 = [];
for (let i = 0; i + 36 <= mem.length; i++) {
    let ok = true;
    for (let j = 0; j < 36; j++) {
        if (mem[i + j] > 31) { ok = false; break; }
    }
    if (ok) candidates31.push(i);
}
log('Found ' + candidates31.length + ' candidates');
for (const off of candidates31.slice(0, 20)) {
    const hex = mem.slice(off, off + 36).map(b => b.toString(16).padStart(2, '0')).join(' ');
    log('  offset 0x' + off.toString(16).padStart(4, '0') + ': ' + hex);
}

// Search for 72-byte blocks (2 bytes per cell) with limited range
log('\n--- 72-byte blocks with all values <= 31 ---');
let candidates72 = [];
for (let i = 0; i + 72 <= mem.length; i++) {
    let ok = true;
    for (let j = 0; j < 72; j++) {
        if (mem[i + j] > 31) { ok = false; break; }
    }
    if (ok) candidates72.push(i);
}
log('Found ' + candidates72.length + ' candidates');
for (const off of candidates72.slice(0, 10)) {
    const hex = mem.slice(off, off + 72).map(b => b.toString(16).padStart(2, '0')).join(' ');
    log('  offset 0x' + off.toString(16).padStart(4, '0') + ': ' + hex);
}

// Look for repeated 36-byte patterns (suggesting multiple levels with similar structure)
log('\n--- REPEATED 36-BYTE PATTERNS ---');
const patternMap = {};
for (let i = 0; i + 36 <= mem.length; i++) {
    const key = mem.slice(i, i + 36).toString('hex');
    if (!patternMap[key]) patternMap[key] = [];
    patternMap[key].push(i);
}
const repeated = Object.entries(patternMap).filter(([k, v]) => v.length > 1);
log('Found ' + repeated.length + ' repeated patterns');
for (const [key, offsets] of repeated.slice(0, 20)) {
    log('  pattern at offsets: ' + offsets.map(o => '0x' + o.toString(16).padStart(4, '0')).join(', ') + ' (' + offsets.length + 'x)');
    const hex = Buffer.from(key, 'hex').map(b => b.toString(16).padStart(2, '0')).join(' ');
    log('    data: ' + hex);
}

// Look for the "bumpy" string area and surrounding data
log('\n--- AREA AROUND "bumpy" STRING (0x749b) ---');
const bumpyOff = 0x749b;
for (let row = -2; row < 6; row++) {
    const start = bumpyOff + row * 16;
    if (start < 0) continue;
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const off = start + c;
        if (off >= mem.length) break;
        const b = mem[off];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + start.toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

// Look for data tables: sequences of small numbers (0-255) that look like level definitions
// Try to find blocks where values are mostly in range 0-10 with some structure
log('\n--- BLOCKS WITH VALUES IN RANGE 0-10 (potential level data) ---');
let levelCandidates = [];
for (let i = 0; i + 36 <= mem.length; i++) {
    let countSmall = 0;
    for (let j = 0; j < 36; j++) {
        if (mem[i + j] <= 10) countSmall++;
    }
    if (countSmall >= 30) { // at least 30 of 36 bytes are small values
        levelCandidates.push({ offset: i, countSmall });
    }
}
log('Found ' + levelCandidates.length + ' candidates');
for (const c of levelCandidates.slice(0, 20)) {
    const hex = mem.slice(c.offset, c.offset + 36).map(b => b.toString(16).padStart(2, '0')).join(' ');
    log('  offset 0x' + c.offset.toString(16).padStart(4, '0') + ' (small: ' + c.countSmall + '/36): ' + hex);
}

// Dump the last 512 bytes of memory (often contains data tables)
log('\n--- LAST 512 BYTES OF MEMORY ---');
const lastStart = mem.length - 512;
for (let row = 0; row < 32; row++) {
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const off = lastStart + row * 16 + c;
        if (off >= mem.length) break;
        const b = mem[off];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + (lastStart + row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

// Dump the area around HL=0x2758 (from header)
const hl = d.readUInt16LE(19);
log('\n--- DUMP AROUND HL=0x' + hl.toString(16) + ' ---');
for (let row = 0; row < 4; row++) {
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const off = hl + row * 16 + c;
        if (off >= mem.length) break;
        const b = mem[off];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + (hl + row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

// Dump around DE=0x369B
const de = d.readUInt16LE(17);
log('\n--- DUMP AROUND DE=0x' + de.toString(16) + ' ---');
for (let row = 0; row < 4; row++) {
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const off = de + row * 16 + c;
        if (off >= mem.length) break;
        const b = mem[off];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + (de + row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

// Dump around BC=0x1621
const bc = d.readUInt16LE(15);
log('\n--- DUMP AROUND BC=0x' + bc.toString(16) + ' ---');
for (let row = 0; row < 4; row++) {
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const off = bc + row * 16 + c;
        if (off >= mem.length) break;
        const b = mem[off];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + (bc + row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

fs.writeFileSync(path.join(__dirname, 'z80_levels.txt'), out.join('\n'));
console.log('Analysis written to tools/z80_levels.txt (' + out.length + ' lines)');
