#!/usr/bin/env node
/**
 * Сборка HTML5-бандла Defold (platform=wasm-web) через HTTP API редактора.
 *
 * Редактор Defold при открытом проекте пишет порт и токен в:
 *   .internal/editor.port
 *   .internal/editor.token
 *
 * Скрипт отправляет POST /bob с опциями bob и командами resolve/build/bundle.
 * Результат bundle для HTML5 оказывается в <bundle-output>/<title>/ — по
 * умолчанию dist/web/bumpy (title из [project] game.project).
 *
 * Использование:
 *   node tools/api_bundle_html5.js                 # variant=debug в dist/web
 *   node tools/api_bundle_html5.js --output dist/web --variant release
 *   node tools/api_bundle_html5.js --architectures wasm-web
 *
 * --architectures wasm-web важен: без него HTML5-бандлер дополнительно требует
 * движок wasm_pthread-web, которого нет в bob.jar (качается с d.defold.com).
 */

const fs = require('fs');
const path = require('path');
const http = require('http');

const ROOT = path.resolve(__dirname, '..');
const INTERNAL = path.join(ROOT, '.internal');
const PORT_FILE = path.join(INTERNAL, 'editor.port');
const TOKEN_FILE = path.join(INTERNAL, 'editor.token');

function parseArgs(argv) {
  const args = { output: 'dist/web', variant: 'debug', architectures: 'wasm-web', timeoutMs: 30 * 60 * 1000 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`Не задано значение для ${a}`);
      return v;
    };
    if (a === '--output' || a === '-o') args.output = next();
    else if (a === '--variant') args.variant = next();
    else if (a === '--architectures') args.architectures = next();
    else if (a === '--timeout') args.timeoutMs = Number(next()) * 1000;
    else if (a === '--help' || a === '-h') {
      console.log('node tools/api_bundle_html5.js [--output dist/web] [--variant debug|release] [--architectures wasm-web] [--timeout sec]');
      process.exit(0);
    } else {
      throw new Error(`Неизвестный аргумент: ${a}`);
    }
  }
  return args;
}

function readTrim(file) {
  return fs.readFileSync(file, 'utf8').trim();
}

function request(port, token, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request(
      {
        host: '127.0.0.1',
        port,
        path: '/bob',
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload),
        },
      },
      (res) => {
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => resolve({ status: res.statusCode, body: data }));
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`Таймаут запроса (${timeoutMs} мс)`)));
    req.on('error', reject);
    req.end(payload);
  });
}

async function main() {
  const args = parseArgs(process.argv);

  if (!fs.existsSync(PORT_FILE) || !fs.existsSync(TOKEN_FILE)) {
    throw new Error(
      'Не найден .internal/editor.port или .internal/editor.token — откройте проект в редакторе Defold.',
    );
  }

  const port = Number(readTrim(PORT_FILE));
  const token = readTrim(TOKEN_FILE);
  if (!Number.isInteger(port) || port <= 0) throw new Error(`Некорректный порт в ${PORT_FILE}`);

  const body = {
    options: {
      platform: 'wasm-web',
      architectures: args.architectures,
      archive: true,
      'bundle-output': args.output,
      variant: args.variant,
    },
    commands: ['resolve', 'build', 'bundle'],
  };

  console.log(`==> bob: platform=wasm-web architectures=${args.architectures} ` +
    `variant=${args.variant} bundle-output=${args.output} (порт ${port})`);

  const res = await request(port, token, body, args.timeoutMs);
  const text = res.body.trim();

  if (res.status !== 200) {
    throw new Error(`HTTP ${res.status}: ${text || '(пустой ответ)'}`);
  }

  let parsed = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    // ответ не JSON — просто выводим как есть
  }

  if (parsed && parsed.success === false) {
    throw new Error(`bob вернул ошибку: ${JSON.stringify(parsed.issues || parsed)}`);
  }

  const indexHtml = path.join(ROOT, args.output, 'bumpy', 'index.html');
  if (!fs.existsSync(indexHtml)) {
    throw new Error(`Сборка завершилась, но ${path.relative(ROOT, indexHtml)} не найден`);
  }

  console.log(`==> Готово: ${path.relative(ROOT, path.dirname(indexHtml))}/`);
}

main().catch((err) => {
  console.error(`Ошибка сборки бандла: ${err.message}`);
  process.exit(1);
});
