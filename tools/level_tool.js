// level_tool.js — единый инструмент описания игровых уровней Bumpy из Bumpy-levels.png.
//
// Bumpy-levels.png = контактная таблица 10x10 экранов (все 100 уровней, уникальны по хэшу).
// Уровень N (1..100): col = (N-1) % 10, row = floor((N-1)/10). Блок: OX=OY=16, шаг X=277, Y=213.
//
// Проверенная геометрия экрана уровня (локальные координаты блока):
//   - линии платформ (верх платформы) y = 29,61,93,125,157,189 (шаг 32);
//   - платформа = серый (LGR=12) прямоугольник 24x4 px;
//   - колонки-слоты: x = 14 + c*40, c=0..5 (платформа занимает [x, x+24]);
//   - поле окружено тёмно-жёлтыми стенами (dYL=8) и белой рамкой (WHT=11); HUD — верхний ряд.
//
// Режимы:
//   node tools/level_tool.js classify <png> [col] [row] [--json]  — сетка платформ + спрайты над ними
//   node tools/level_tool.js floors   <png> [col] [row]           — точные x-диапазоны платформ на каждой линии
//   node tools/level_tool.js dump     <png> [col] [row] [yFrom] [yTo] — сырые пиксельные строки (легенда цветов)
//
// Легенда палитры ZX: M=мagenta m=dM B=blue C=cyan c=dC G=green g=dG Y=yellow y=dY R=red r=dR #=white +=light-gray .=black
const fs = require('fs');
const zlib = require('zlib');

function loadPng(path) {
  const d = fs.readFileSync(path);
  let off = 8, w = 0, h = 0, bd = 0, ct = 0; const idat = [];
  while (off + 8 <= d.length) {
    const len = d.readUInt32BE(off);
    const t = d.slice(off + 4, off + 8).toString('ascii');
    const data = d.slice(off + 8, off + 8 + len);
    if (t === 'IHDR') { w = data.readUInt32BE(0); h = data.readUInt32BE(4); bd = data[8]; ct = data[9]; }
    else if (t === 'IDAT') idat.push(data);
    else if (t === 'IEND') break;
    off += 12 + len;
  }
  const stride = Math.ceil(w * bd / 8);
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const mask = (1 << bd) - 1;
  const px = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)];
    const src = raw.slice(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
    const cur = new Uint8Array(w);
    for (let x = 0; x < w; x++) {
      const bi = Math.floor(x * bd / 8), sh = 8 - (x * bd) % 8 - bd;
      let v = (src[bi] >> sh) & mask;
      const a = x > 0 ? cur[x - 1] : 0, b = y > 0 ? px[(y - 1) * w + x] : 0, c = (x > 0 && y > 0) ? px[(y - 1) * w + x - 1] : 0;
      switch (f) { case 1: v += a; break; case 2: v += b; break; case 3: v += Math.floor((a + b) / 2); break;
        case 4: { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v += (pa <= pb && pa <= pc) ? a : (pb <= pc ? b : c); break; } }
      cur[x] = v & mask;
    }
    px.set(cur, y * w);
  }
  return { w, h, px };
}

const NAME = ['MAG','dMG','BLU','CYA','dCY','GRN','dGR','YEL','dYL','RED','dRD','WHT','LGR','BLK'];
const CH = ['M','m','B','C','c','G','g','Y','y','R','r','#','+','.'];
// цвета спрайтов (без чёрного фона, белой рамки, серых платформ и тёмно-жёлтых стен)
const SPRITE_COLORS = [0,1,2,3,4,5,6,7,9,10];

const FLOOR = [29, 61, 93, 125, 157, 189]; // верх платформы на каждом этаже
const BOX0 = 14, PITCH = 40, BW = 24;      // x-геометрия: платформа в колонке c на [BOX0+c*PITCH .. +BW]
const FIELD_TOP = 13;                      // низ HUD / верх поля
const N = 6;

function classify(pngPath, col, row, asJson) {
  const img = loadPng(pngPath);
  const { w, px } = img;
  const OX = 16, OY = 16, PX = 277, PY = 213;
  const x0 = OX + col * PX, y0 = OY + row * PY;
  const P = (lx, ly) => px[(y0 + ly) * w + (x0 + lx)];

  const floors = [];
  for (let r = 0; r < N; r++) {
    const fy = FLOOR[r];
    const plat = [];
    for (let c = 0; c < N; c++) {
      const bx0 = BOX0 + c * PITCH + 2, bx1 = BOX0 + c * PITCH + BW - 2;
      let gray = 0;
      for (let x = bx0; x <= bx1; x++) if (P(x, fy) === 12) gray++;
      plat.push(gray >= BW / 2 ? 1 : 0);
    }
    const laneTop = (r === 0) ? FIELD_TOP : FLOOR[r - 1] + 5;
    const sprites = [];
    for (let c = 0; c < N; c++) {
      const sx0 = BOX0 + c * PITCH, sx1 = BOX0 + (c + 1) * PITCH - 1;
      const counts = {};
      for (let y = laneTop; y < fy - 1; y++) {
        for (let x = sx0; x <= sx1; x++) {
          const v = P(x, y);
          if (SPRITE_COLORS.indexOf(v) >= 0) counts[v] = (counts[v] || 0) + 1;
        }
      }
      for (const k of Object.keys(counts).sort((a, b) => b - a)) {
        if (counts[k] >= 8) sprites.push({ floor: r, col: c, color: NAME[k], px: counts[k] });
      }
    }
    floors.push({ floor: r, platforms: plat });
    if (asJson) floors[floors.length - 1].sprites = sprites;
    else {
      console.log('floor ' + r + '  plat: ' + plat.map(v => v ? 'P' : '.').join(''));
      const cells = [];
      for (let c = 0; c < N; c++) {
        const parts = sprites.filter(s => s.col === c).map(s => s.color + '(' + s.px + ')');
        cells.push(parts.length ? parts.join(' ') : '-');
      }
      console.log('         lane: ' + cells.join(' | '));
    }
  }
  if (asJson) {
    const lvl = row * 10 + col + 1; // номер уровня: таблица 10x10, уровень 1 в блоке (0,0)
    console.log(JSON.stringify({ level: lvl, block: { col, row }, floors }, null, 2));
  }
}

function floors(pngPath, col, row) {
  const img = loadPng(pngPath);
  const { w, px } = img;
  const OX = 16, OY = 16, PX = 277, PY = 213;
  const x0 = OX + col * PX, y0 = OY + row * PY;
  const P = (lx, ly) => px[(y0 + ly) * w + (x0 + lx)];
  for (let r = 0; r < FLOOR.length; r++) {
    const y = FLOOR[r];
    const runs = [];
    let i = 0;
    while (i < 260) {
      if (P(i, y) === 12) {
        const st = i;
        while (i < 260 && P(i, y) === 12) i++;
        runs.push(st + '-' + (i - 1));
      } else i++;
    }
    console.log('floor ' + r + ' y=' + y + ' boxes: [' + runs.join(', ') + ']');
  }
}

function dump(pngPath, col, row, yFrom, yTo) {
  const img = loadPng(pngPath);
  const { w, px } = img;
  const OX = 16, OY = 16, PX = 277, PY = 213;
  const x0 = OX + col * PX, y0 = OY + row * PY;
  const P = (lx, ly) => px[(y0 + ly) * w + (x0 + lx)];
  for (let y = yFrom; y <= yTo; y++) {
    let s = '';
    for (let x = 0; x < 271; x++) s += CH[P(x, y)];
    console.log('y=' + y + ' |' + s + '|');
  }
}

const [cmd, pngPath, a3, a4, a5, a6] = process.argv.slice(2);
const col = parseInt(a3 || '0', 10);
const row = (a4 && !isNaN(parseInt(a4, 10))) ? parseInt(a4, 10) : 0;

switch (cmd) {
  case 'classify': classify(pngPath, col, row, process.argv.indexOf('--json') >= 0); break;
  case 'floors': floors(pngPath, col, row); break;
  case 'dump': dump(pngPath, col, row, parseInt(a5 || '26', 10), parseInt(a6 || '33', 10)); break;
  default: console.log('usage: node tools/level_tool.js classify|floors|dump <png> [col] [row] [--json]'); process.exit(1);
}
