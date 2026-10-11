const fs = require('fs');
const path = require('path');
const out = [];
const log = (...a) => out.push(a.join(' '));

const d = fs.readFileSync(path.join(__dirname, '..', 'Bumpy (1989)(Loriciels).z80'));
log('=== Z80 SNAPSHOT ANALYSIS ===');
log('file size:', d.length);

// Header
log('\n--- HEADER (32 bytes) ---');
log('machine: 0x' + d.readUInt16LE(0).toString(16));
log('tape blocks: ' + d[2]);
log('flags: ' + d[3]);
log('IY: 0x' + d.readUInt16LE(4).toString(16));
log('IX: 0x' + d.readUInt16LE(6).toString(16));
log('R: ' + d[8]);
log('PC: 0x' + d.readUInt16LE(9).toString(16));
log('SP: 0x' + d.readUInt16LE(11).toString(16));
log('AF: 0x' + d.readUInt16LE(13).toString(16));
log('BC: 0x' + d.readUInt16LE(15).toString(16));
log('DE: 0x' + d.readUInt16LE(17).toString(16));
log('HL: 0x' + d.readUInt16LE(19).toString(16));
log('I: 0x' + d[21].toString(16));
log('IF: ' + (d[22] & 3));

const mem = d.slice(32);
log('\n--- MEMORY ---');
log('memory bytes:', mem.length, '(0x' + mem.length.toString(16) + ')');

// First / last nonzero
let first = -1, last = -1;
for (let p = 0; p < mem.length; p++) if (mem[p] !== 0) { first = p; break; }
for (let p = mem.length - 1; p >= 0; p--) if (mem[p] !== 0) { last = p; break; }
log('first nonzero at offset ' + first + ' (0x' + first.toString(16) + ')');
log('last nonzero at offset ' + last + ' (0x' + last.toString(16) + ')');

// Zero runs >= 16 bytes
log('\n--- ZERO RUNS (>=16 bytes) ---');
let i = 0;
while (i < mem.length) {
    if (mem[i] === 0) {
        let s = i;
        while (i < mem.length && mem[i] === 0) i++;
        if (i - s >= 16) log('  offset 0x' + s.toString(16).padStart(4, '0') + ' len ' + (i - s));
    } else i++;
}

// Non-zero regions (gaps between zero runs)
log('\n--- NON-ZERO REGIONS ---');
let nz = [];
i = 0;
while (i < mem.length) {
    if (mem[i] !== 0) {
        let s = i;
        while (i < mem.length && mem[i] !== 0) i++;
        nz.push([s, i - 1]);
    } else i++;
}
for (const [s, e] of nz) log('  offset 0x' + s.toString(16).padStart(4, '0') + ' .. 0x' + e.toString(16).padStart(4, '0') + ' len ' + (e - s + 1));

// ASCII strings >= 4 chars
log('\n--- ASCII STRINGS (>=4 chars) ---');
let strCount = 0;
i = 0;
while (i < mem.length) {
    if (mem[i] >= 0x20 && mem[i] < 0x7f) {
        let s = i;
        while (i < mem.length && mem[i] >= 0x20 && mem[i] < 0x7f) i++;
        if (i - s >= 4) {
            const str = mem.slice(s, i).toString('latin1');
            log('  offset 0x' + s.toString(16).padStart(4, '0') + ' len ' + (i - s) + ' : ' + JSON.stringify(str));
            strCount++;
        }
    } else i++;
}
log('total strings: ' + strCount);

// ZX Spectrum character set check: look for "BUMPY" or "LORICIELLS" in various encodings
log('\n--- SEARCH FOR KEY STRINGS ---');
const targets = ['BUMPY', 'bumpy', 'LORICIELLS', 'loriciels', 'COPYRIGHT', 'PRESS', 'SPACE'];
for (const t of targets) {
    const buf = Buffer.from(t, 'latin1');
    let idx = mem.indexOf(buf);
    while (idx >= 0) {
        log('  found "' + t + '" at offset 0x' + idx.toString(16).padStart(4, '0'));
        idx = mem.indexOf(buf, idx + 1);
    }
}

// Check if memory looks like it could be a partial dump:
// ZX Spectrum 48K has RAM at 0x0000-0xBFFF (48KB)
// If the file is 36677 bytes total, memory is 36645 bytes = 0x8FCD
log('\n--- SIZE ANALYSIS ---');
log('memory size 0x' + mem.length.toString(16) + ' = ' + mem.length);
log('48K would be 0xC000 = 49152');
log('128K would be 0x20000 = 131072');
log('diff from 48K: ' + (49152 - mem.length));

// Dump hex of first 256 bytes of memory
log('\n--- MEMORY DUMP (first 256 bytes) ---');
for (let row = 0; row < 16; row++) {
    let hex = '', asc = '';
    for (let c = 0; c < 16; c++) {
        const b = mem[row * 16 + c];
        hex += b.toString(16).padStart(2, '0') + ' ';
        asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    log('  0x' + (row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
}

// Dump around PC=0x3F61 if in range
const pc = d.readUInt16LE(9);
if (pc < mem.length) {
    log('\n--- MEMORY DUMP around PC=0x' + pc.toString(16) + ' ---');
    const start = Math.max(0, pc - 8);
    for (let row = 0; row < 4; row++) {
        let hex = '', asc = '';
        for (let c = 0; c < 16; c++) {
            const off = start + row * 16 + c;
            if (off >= mem.length) break;
            const b = mem[off];
            hex += b.toString(16).padStart(2, '0') + ' ';
            asc += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
        }
        log('  0x' + (start + row * 16).toString(16).padStart(4, '0') + '  ' + hex + ' |' + asc + '|');
    }
}

fs.writeFileSync(path.join(__dirname, 'z80_analysis.txt'), out.join('\n'));
console.log('Analysis written to tools/z80_analysis.txt (' + out.length + ' lines)');
