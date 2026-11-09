#!/usr/bin/env python3
"""Часовой генератор уровней Bumpy: один проходимый уровень за запуск.

Запуск по расписанию (cron или systemd timer), раз в час:

    # cron (каждый час в 5 минут)
    5 * * * * cd /path/to/bumpy && /usr/bin/python3 tools/gen_hourly.py >> /var/log/bumpy-gen.log 2>&1

    # systemd timer: OnCalendar=hourly + ExecStart=... tools/gen_hourly.py

Что делает запуск:
  1. Спрашивает у backend следующий seed (GET /api/levels/stats) — фактически
     seed = «максимальный сохранённый + 1», чтобы последовательность не
     зацикливалась между запусками.
  2. Генерирует кандидатов tools/gen_level.py, пока решатель
     (tools/solve_level.py: is_solvable) не подтвердит проходимость.
  3. Считает минимальный стартовый набор предметов (solve) — игра выдаёт его
     в режиме Adventure.
  4. Сохраняет РОВНО один уровень через POST /api/levels. Сервер принимает
     только status = "solvable", поэтому непроверенный уровень в БД не попадёт.

Адрес backend и ключ берутся из:
  --api-url / BUMPY_API_URL (по умолчанию http://127.0.0.1:8000)
  --api-key / BUMPY_API_KEY (по умолчанию пусто — доступ открыт).

Использование:
    python3 tools/gen_hourly.py                      # один уровень
    python3 tools/gen_hourly.py --dry-run            # сгенерировать, но не писать
    python3 tools/gen_hourly.py --level 7            # сложность под уровень 7
    python3 tools/gen_hourly.py --count 3            # три уровня за запуск
    python3 tools/gen_hourly.py --loop 3600          # крутиться в контейнере
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_level  # noqa: E402

DEFAULT_API_URL = os.environ.get("BUMPY_API_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.environ.get("BUMPY_API_KEY", "")


# --- HTTP -------------------------------------------------------------------


def _request(method: str, url: str, payload: dict | None,
             api_key: str, timeout: float = 30.0) -> tuple[int, dict | str]:
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


def fetch_stats(api_url: str, api_key: str) -> dict:
    """Статистика уровней в БД: total и latest_at (пусто при ошибке)."""
    status, data = _request("GET", f"{api_url}/api/levels/stats", None, api_key)
    if status != 200 or not isinstance(data, dict):
        print(f"  stats недоступны ({status}): {data}", file=sys.stderr)
        return {}
    return data


def next_seed(api_url: str, api_key: str) -> int:
    """Seed для новой генерации: текущее время + число уровней в БД.

    MAX(seed) с сервера не отдаётся (stats только считает записи), поэтому
    берём производную от времени и счётчика: разные запуски почти наверняка
    дают разные seed'ы, а при сбое stats (total = 0) остаётся чистое время —
    последовательность всё равно продолжится.
    """
    stats = fetch_stats(api_url, api_key)
    total = int(stats.get("total") or 0)
    return int(time.time()) * 1000 + total


def post_level(api_url: str, api_key: str, payload: dict) -> tuple[int, dict | str]:
    return _request("POST", f"{api_url}/api/levels", payload, api_key)


# --- генерация --------------------------------------------------------------


def build_payload(seed: int, level_number: int, node_cap: int, attempts: int,
                  min_items: int = gen_level.MIN_REQUIRED_ITEMS,
                  min_interest: float = gen_level.MIN_INTEREST,
                  interest_pool: int = gen_level.DEFAULT_INTEREST_POOL,
                  on_attempt=None) -> dict | None:
    """Сгенерировать подходящий уровень и подготовить тело запроса POST.

    Требования по снаряжению берутся из того же прохода решателя, что и
    статус проходимости (gen_level.evaluate): дополнительный вызов solve()
    здесь не нужен и только замедлял бы генерацию в разы.

    Отбор идёт по «человеческой» интересности (tools/level_interest.py):
    генератор берёт лучший из `interest_pool` подходящих кандидатов, а уровни
    ниже `min_interest` отбрасываются как скучные.
    """
    level = gen_level.generate_playable(
        seed, level_number, attempts=attempts, node_cap=node_cap,
        min_items=min_items, min_interest=min_interest,
        interest_pool=interest_pool, on_attempt=on_attempt)
    if level is None:
        return None

    status, required = gen_level.evaluate(level, node_cap=node_cap)
    if status != "solvable":
        return None
    if sum(required) < min_items:
        # Требование «хотя бы один предмет»: без него уровень слишком простой
        return None

    req = {
        "drops": required[0],
        "keys": required[1],
        "hammers": required[2],
    }

    # в payload убираем служебные поля генератора: main/level/level.script
    # читает только поля формата levels.json. `interest` и `interest_parts` —
    # диагностика генератора: они нужны только логу и отчётам, а не игре.
    body = {
        key: value for key, value in level.items()
        if key not in ("seed", "generated", "requirements",
                       "interest", "interest_parts")
    }
    return {
        "seed": int(level["seed"]),
        "level": int(level_number),
        "payload": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        "status": "solvable",
        "drops": int(req.get("drops", 0)),
        "keys": int(req.get("keys", 0)),
        "hammers": int(req.get("hammers", 0)),
        "generator": "tools/gen_hourly.py",
        # «человеческая» интересность выбранного кандидата (0..100) — только
        # для логов: сервер это поле не хранит
        "interest": float(level.get("interest", 0.0)),
    }


def run_once(api_url: str, api_key: str, level_number: int, node_cap: int,
             attempts: int, dry_run: bool,
             seed: int | None = None,
             min_items: int = gen_level.MIN_REQUIRED_ITEMS,
             min_interest: float = gen_level.MIN_INTEREST,
             interest_pool: int = gen_level.DEFAULT_INTEREST_POOL,
             ) -> tuple[bool, int | None]:
    """Один цикл: сгенерировать и сохранить ровно один уровень.

    Возвращает (сохранён ли уровень, seed найденного уровня). Второй элемент
    нужен `--count`: следующий уровень должен начинать перебор со следующего
    seed'а, иначе несколько уровней за запуск оказались бы одинаковыми.
    """
    if seed is None:
        seed = next_seed(api_url, api_key)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] генерация: seed={seed} "
          f"level={level_number}")

    payload = build_payload(seed, level_number, node_cap, attempts,
                            min_items=min_items, min_interest=min_interest,
                            interest_pool=interest_pool,
                            on_attempt=lambda s, st:
                            print(f"  seed {s}: {st}") if st != "impossible" else None)
    if payload is None:
        print("  подходящий уровень не найден — пропуск запуска", file=sys.stderr)
        return False, None

    found_seed = int(payload["seed"])
    print(f"  найден: seed={found_seed} "
          f"требуется drops={payload['drops']} keys={payload['keys']} "
          f"hammers={payload['hammers']} interest={payload['interest']:.1f}")

    if dry_run:
        print("  --dry-run: в БД не пишу")
        return True, found_seed

    status, data = post_level(api_url, api_key, payload)
    if status in (200, 201):
        level_id = data.get("level_id") if isinstance(data, dict) else None
        print(f"  сохранено в БД: level_id={level_id}")
        return True, found_seed
    print(f"  ошибка сохранения ({status}): {data}", file=sys.stderr)
    return False, found_seed


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Часовой генератор проходимых уровней Bumpy.")
    ap.add_argument("--api-url", default=DEFAULT_API_URL,
                    help=f"адрес backend (по умолчанию {DEFAULT_API_URL})")
    ap.add_argument("--api-key", default=DEFAULT_API_KEY,
                    help="API-ключ (заголовок X-Api-Key), если включён")
    ap.add_argument("--level", type=int, default=1,
                    help="номер уровня (влияет на сложность)")
    ap.add_argument("--node-cap", type=int, default=400000,
                    help="лимит узлов решателя на кандидата")
    ap.add_argument("--attempts", type=int, default=200,
                    help="сколько seed'ов перебрать до отказа")
    ap.add_argument("--count", type=int, default=1,
                    help="сколько уровней сгенерировать за запуск")
    ap.add_argument("--min-items", type=int,
                    default=gen_level.MIN_REQUIRED_ITEMS,
                    help=("сколько предметов уровень обязан требовать на старте "
                          f"(по умолчанию {gen_level.MIN_REQUIRED_ITEMS}; "
                          "0 — не требовать)"))
    ap.add_argument("--min-interest", type=float,
                    default=gen_level.MIN_INTEREST,
                    help=("минимальная «человеческая» интересность 0..100 "
                          f"(по умолчанию {gen_level.MIN_INTEREST}; "
                          "0 — не проверять)"))
    ap.add_argument("--interest-pool", type=int,
                    default=gen_level.DEFAULT_INTEREST_POOL,
                    help=("из скольких подходящих кандидатов выбрать самый "
                          f"интересный (по умолчанию "
                          f"{gen_level.DEFAULT_INTEREST_POOL})"))
    ap.add_argument("--dry-run", action="store_true",
                    help="сгенерировать, но не сохранять в БД")
    ap.add_argument("--loop", type=int, default=0,
                    help="работать постоянно с интервалом N секунд (для контейнера)")
    args = ap.parse_args()

    api_url = args.api_url.rstrip("/")

    def cycle() -> int:
        saved = 0
        # seed следующего уровня: сдвигается после каждой удачной генерации,
        # иначе несколько уровней за запуск оказались бы одинаковыми
        seed = None
        for _ in range(max(1, args.count)):
            ok, found = run_once(api_url, args.api_key, args.level,
                                 args.node_cap, args.attempts, args.dry_run,
                                 seed=seed, min_items=args.min_items,
                                 min_interest=args.min_interest,
                                 interest_pool=args.interest_pool)
            if ok:
                saved += 1
            if found is not None:
                seed = found + 1
        print(f"итог: сохранено {saved} из {max(1, args.count)}")
        return saved

    if args.loop > 0:
        print(f"режим цикла: интервал {args.loop} с, backend {api_url}")
        while True:
            cycle()
            time.sleep(args.loop)
    cycle()


if __name__ == "__main__":
    main()
