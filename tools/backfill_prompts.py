#!/usr/bin/env python3
"""Дозаполнение промтов у уже сохранённых уровней.

Уровни, созданные до появления промтов (или генератором, который их ещё не
присылал), лежат в БД без правила генерации. Скрипт проходит по таким записям,
собирает промт из payload (backend/app/level_prompts.py) и отправляет его на
сервер через PUT /api/levels/{id}/prompt.

Схему прохождения скрипт по умолчанию не восстанавливает: для этого нужен
решатель (tools/solve_level.py), а он на порядки медленнее сборки промта.
Если нужен и план — запускайте с --with-plan (на большой БД это долго).

Использование:
    python3 tools/backfill_prompts.py                 # все уровни без промта
    python3 tools/backfill_prompts.py --limit 50      # только 50 записей
    python3 tools/backfill_prompts.py --with-plan     # + схема прохождения
    python3 tools/backfill_prompts.py --dry-run       # показать, что будет
    python3 tools/backfill_prompts.py --api-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from backend.app import level_prompts  # noqa: E402

DEFAULT_API_URL = os.environ.get("BUMPY_API_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.environ.get("BUMPY_API_KEY", "")


def request(method: str, url: str, payload: dict | None,
            api_key: str, timeout: float = 30.0) -> tuple[int, dict | list | str]:
    """HTTP-запрос как в tools/gen_hourly.py (без сторонних библиотек)."""
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if api_key:
        headers["X-Api-Key"] = api_key
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body) if body else {}
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return exc.code, body
    except urllib.error.URLError as exc:
        return 0, f"backend недоступен: {exc}"


def plan_for(level: dict) -> list[str] | None:
    """Схема прохождения через решатель (--with-plan)."""
    try:  # pragma: no cover - зависит от tools/solve_level.py
        import solve_level as sv  # noqa: PLC0415

        res = sv.solve(sv.Level(level), node_cap=400000, legacy=True,
                       allow_fallback=True)
        if res.get("status") != "solvable":
            return None
        return list(res.get("actions") or [])
    except Exception as exc:  # pragma: no cover - решатель не обязателен
        print(f"  решатель недоступен ({exc}) — промт без схемы прохождения",
              file=sys.stderr)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Дозаполнить промты уровней в БД Bumpy.")
    ap.add_argument("--api-url", default=DEFAULT_API_URL,
                    help=f"адрес backend (по умолчанию {DEFAULT_API_URL})")
    ap.add_argument("--api-key", default=DEFAULT_API_KEY,
                    help="API-ключ (заголовок X-Api-Key), если включён")
    ap.add_argument("--limit", type=int, default=500,
                    help="сколько записей обработать за запуск")
    ap.add_argument("--page", type=int, default=100,
                    help="размер пачки при выборке уровней без промта")
    ap.add_argument("--with-plan", action="store_true",
                    help="добавить схему прохождения (медленно: решатель)")
    ap.add_argument("--dry-run", action="store_true",
                    help="ничего не писать, только показать")
    args = ap.parse_args()

    api_url = args.api_url.rstrip("/")
    remaining = max(1, args.limit)
    done = 0
    failed = 0

    while remaining > 0:
        page = min(max(1, args.page), remaining)
        status, data = request(
            "GET", f"{api_url}/api/levels/prompts/missing?limit={page}",
            None, args.api_key)
        if status != 200 or not isinstance(data, list):
            print(f"не удалось получить список уровней без промта "
                  f"({status}): {data}", file=sys.stderr)
            break
        if not data:
            print("уровней без промта нет")
            break

        for item in data:
            level_id = item.get("level_id")
            raw = item.get("payload")
            if not level_id or not isinstance(raw, str):
                continue
            try:
                level = json.loads(raw)
            except ValueError:
                print(f"  {level_id}: битый payload — пропуск", file=sys.stderr)
                failed += 1
                continue
            # требования уровня лежат в самой записи, а не в payload
            level.update({
                "drops": int(item.get("drops") or 0),
                "keys": int(item.get("keys") or 0),
                "hammers": int(item.get("hammers") or 0),
            })
            plan = plan_for(level) if args.with_plan else None
            info = level_prompts.build(level, plan=plan,
                                       generator="tools/backfill_prompts.py")
            signature = json.dumps(
                info["signature"], ensure_ascii=False, separators=(",", ":"))
            print(f"  {level_id}: промт {len(info['prompt'])} символов"
                  + (f", схема {len(plan)} действий" if plan else ""))
            if args.dry_run:
                done += 1
                continue
            code, resp = request(
                "PUT", f"{api_url}/api/levels/{level_id}/prompt",
                {
                    "prompt": info["prompt"],
                    "prompt_version": int(info["version"]),
                    "signature": signature,
                },
                args.api_key)
            if code == 200:
                done += 1
            else:
                failed += 1
                print(f"  {level_id}: ошибка сохранения ({code}): {resp}",
                      file=sys.stderr)

        remaining -= len(data)
        if len(data) < page:
            break

    print(f"итог: обновлено промтов {done}, ошибок {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
