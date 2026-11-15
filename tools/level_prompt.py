#!/usr/bin/env python3
"""CLI к промтам уровней Bumpy.

Сама логика живёт в backend/app/level_prompts.py: промт нужен и генератору
(tools/gen_hourly.py), и серверу (когда уровень пришёл без промта, а также при
бэкфилле старых записей), поэтому копия в tools была бы третьим источником
истины. Здесь — только тонкая обёртка: путь к backend добавляется в sys.path,
дальше вызывается общий модуль.

Использование:
    python3 tools/level_prompt.py level.json           # текст промта
    python3 tools/level_prompt.py level.json --json    # промт + подпись
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from backend.app import level_prompts as lp  # noqa: E402

# Публичный интерфейс обёртки — ровно то, чем пользуется генератор.
PROMPT_VERSION = lp.PROMPT_VERSION
build = lp.build
signature = lp.signature
similarity = lp.similarity
too_similar = lp.too_similar
load_signature = lp.load_signature


def main() -> None:  # pragma: no cover - утилитарный запуск
    import argparse

    ap = argparse.ArgumentParser(description="Промт (правило генерации) уровня Bumpy.")
    ap.add_argument("level", help="JSON-файл уровня (формат levels.json)")
    ap.add_argument("--json", action="store_true", help="вывести всё в JSON")
    args = ap.parse_args()

    with open(args.level, encoding="utf-8") as fh:
        level = json.load(fh)
    info = build(level)
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(info["prompt"])


if __name__ == "__main__":  # pragma: no cover
    main()
