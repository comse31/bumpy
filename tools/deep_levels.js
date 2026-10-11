const fs = require('fs');
const path = require('path');
const out = [];
const log = (...a) => out.push(a.join(' '));

const d = fs.readFileSync(path.join(__dirname, '..', 'Bumpy (1989)(Loriciels).z80'));
const mem = d.slice(32);

log('=== DEEP LEVEL ANALYSIS ===');

// Helper: dump a region with hex + ascii
function dumpRegion(start, len, label) {
    log('\n--- ' + label + ' (0x' + start.toString(16).padStart(4, '0') + ', len=' + len + ') ---');
    for (let row = 0; row < Math.ceil(len / 16); row++) {
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

// Helper: format a 36-byte block as a 6x6 grid
function formatGrid(offset) {
    const block = mem.slice(offset, offset + 36);
    let lines = [];
    for (let row = 0; row < 6; row++) {
        let line = '  ';
        for (let col = 0; col < 6; col++) {
            const v = block[row * 6 + col];
            line += String(v).padStart(2, ' ') + ' ';
        }
        lines.push(line);
    }
    return lines.join('\n');
}

// 1. Examine area around 0x0fd1 (most promising candidate)
dumpRegion(0x0f80, 128, 'AREA AROUND 0x0FD1');
log('\nGrid at 0x0fd1:');
log(formatGrid(0x0fd1));

// Check if there are more 36-byte blocks nearby (potential multiple levels)
log('\n--- CHECKING FOR CONSECUTIVE 36-BYTE BLOCKS NEAR 0x0FD1 ---');
for (let off = 0x0f80; off < 0x1200; off++) {
    let allSmall = true;
    for (let j = 0; j < 36; j++) {
        if (mem[off + j] > 15) { allSmall = false; break; }
    }
    if (allSmall) {
        // Check if this is a "clean" start (previous byte is 0 or boundary)
        const prev = off > 0 ? mem[off - 1] : 255;
        log('  offset 0x' + off.toString(16).padStart(4, '0') + ' (prev=0x' + prev.toString(16) + '): ' + 
            mem.slice(off, off + 36).map(b => b.toString()).join(','));
    }
}

// 2. Examine area around 0x0ab7
dumpRegion(0x0a80, 128, 'AREA AROUND 0x0AB7');
log('\nGrid at 0x0ab7:');
log(formatGrid(0x0ab7));

// 3. Examine area around 0x0dca
dumpRegion(0x0d80, 128, 'AREA AROUND 0x0DCA');
log('\nGrid at 0x0dca:');
log(formatGrid(0x0dca));

// 4. Look for level data tables: sequences of small numbers with structure
// Strategy: find blocks where values are in range 0-15 AND the block has some "sparsity" 
// (many zeros, suggesting empty cells)
log('\n--- SPARSE 36-BYTE BLOCKS (values 0-15, at least 10 zeros) ---');
let sparseBlocks = [];
for (let i = 0; i + 36 <= mem.length; i++) {
    let zeroCount = 0;
    let maxVal = 0;
    for (let j = 0; j < 36; j++) {
        if (mem[i + j] === 0) zeroCount++;
        if (mem[i + j] > maxVal) maxVal = mem[i + j];
    }
    if (maxVal <= 15 && zeroCount >= 10) {
        sparseBlocks.push({ offset: i, zeroCount, maxVal });
    }
}
log('Found ' + sparseBlocks.length + ' sparse blocks');
for (const b of sparseBlocks.slice(0, 30)) {
    log('  offset 0x' + b.offset.toString(16).padStart(4, '0') + ' zeros=' + b.zeroCount + ' max=' + b.maxVal);
}

// 5. Look for the level count / level index table
// In many games, there's a table of pointers or indices to level data
log('\n--- SEARCH FOR LEVEL INDEX TABLES ---');
// Look for sequences of small numbers that could be level indices (0-20)
for (let i = 0; i + 20 <= mem.length; i++) {
    // Check if we have a sequence of values that look like level indices
    let looksLikeIndex = true;
    for (let j = 0; j < 10; j++) {
        if (mem[i + j] > 30) { looksLikeIndex = false; break; }
    }
    if (looksLikeIndex) {
        // Check if the values are mostly small and have some pattern
        const vals = mem.slice(i, i + 10);
        const unique = new Set(vals).size;
        if (unique <= 5 && vals[0] === 0) {
            log('  potential index table at 0x' + i.toString(16).padStart(4, '0') + ': ' + 
                vals.map(v => v.toString()).join(','));
        }
    }
}

// 6. Look for the "GAME" menu area and trace forward to find level data
dumpRegion(0x63e0, 128, 'MENU AREA (0x63E0)');

// 7. Look at the area right after the "bumpy" tape name - often level data follows
dumpRegion(0x7490, 128, 'AFTER TAPE NAME (0x7490)');

// 8. Search for blocks that look like they could be level definitions with a header byte
// Pattern: [header_byte] [36 bytes of grid data]
log('\n--- BLOCKS WITH HEADER + 36-BYTE GRID ---');
for (let i = 0; i + 37 <= mem.length; i++) {
    // Check if byte at i is a small number (potential level index)
    // and bytes i+1 to i+36 are all <= 15
    const header = mem[i];
    let gridOk = true;
    for (let j = 1; j <= 36; j++) {
        if (mem[i + j] > 15) { gridOk = false; break; }
    }
    if (gridOk && header <= 20) {
        // Additional check: the grid should have some structure
        const grid = mem.slice(i + 1, i + 37);
        let zeroCount = 0;
        for (const b of grid) if (b === 0) zeroCount++;
        if (zeroCount >= 5) {
            log('  offset 0x' + i.toString(16).padStart(4, '0') + ' header=' + header + ' zeros=' + zeroCount);
        }
    }
}

// 9. Look for the specific pattern of Bumpy levels
// Bumpy has levels with platforms, walls, items
// Cell types might be: 0=empty, 1=platform, 2=wall, 3=spike, etc.
// Let's look for blocks where values are in range 0-8 (common cell type range)
log('\n--- BLOCKS WITH VALUES IN RANGE 0-8 (36 bytes) ---');
let range8Blocks = [];
for (let i = 0; i + 36 <= mem.length; i++) {
    let ok = true;
    for (let j = 0; j < 36; j++) {
        if (mem[i + j] > 8) { ok = false; break; }
    }
    if (ok) range8Blocks.push(i);
}
log('Found ' + range8Blocks.length + ' blocks');
// Group consecutive/nearby blocks
let groups = [];
let currentGroup = [range8Blocks[0]];
for (let i = 1; i < range8Blocks.length; i++) {
    if (range8Blocks[i] - range8Blocks[i-1] <= 4) {
        currentGroup.push(range8Blocks[i]);
    } else {
        groups.push(currentGroup);
        currentGroup = [range8Blocks[i]];
    }
}
groups.push(currentGroup);
log('Found ' + groups.length + ' groups');
for (const g of groups.slice(0, 20)) {
    const start = g[0];
    log('  group at 0x' + start.toString(16).padStart(4, '0') + ' (' + g.length + ' candidates): ');
    // Show the first candidate's grid
    log(formatGrid(start));
}

// 10. Dump the area around 0x0f1c (another candidate with value 17)
dumpRegion(0x0f00, 96, 'AREA AROUND 0x0F1C');

fs.writeFileSync(path.join(__dirname, 'z80_deep.txt'), out.join('\n'));
console.log('Analysis written to tools/z80_deep.txt (' + out.length + ' lines)');
