"""Дымовой тест API: прогоняет реальные сценарии клиента игры.

Запуск (внутри контейнера или локально при установленных зависимостях):
    python -m backend.tests.smoke_test http://127.0.0.1:8000

Проверяется ровно то, что делает игра (main/remote_db.lua):
  1. health отвечает и видит БД;
  2. PUT создаёт профиль игрока (имя, визиты, уровень, жизни, карман);
  3. повторный PUT обновляет запись, а max_level/visits только растут;
  4. GET отдаёт сохранённые значения и историю событий;
  5. POST события добавляет запись в историю;
  6. лидерборд отдаёт игрока;
  7. некорректный player_id отклоняется (422);
  8. DELETE удаляет профиль;
  9. вход по имени и паролю: регистрация нового имени, вход с верным и
     неверным паролем, повторная привязка, уникальность default-имён.

Скрипт не требует pytest и сторонних библиотек — только стандартный Python.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PLAYER_ID = "smoketest0001"


def request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        raise SystemExit(1)


def main() -> None:
    print(f"Backend: {BASE}")

    # 1. health
    status, health = request("GET", "/api/health")
    check("health 200", status == 200, str(health))
    check("БД доступна", health.get("database") == "ok", str(health))

    # убрать остатки предыдущего прогона
    request("DELETE", f"/api/players/{PLAYER_ID}")

    # 2. создание профиля
    snapshot = {
        "player_id": PLAYER_ID,
        "name": "Smoke Tom",
        "visits": 3,
        "level": 5,
        "max_level": 7,
        "lives": 2,
        "drops": 4,
        "keys": 1,
        "hammers": 0,
        "client_version": "1.0.0",
        "platform": "HTML5",
    }
    status, player = request("PUT", f"/api/players/{PLAYER_ID}", snapshot)
    check("PUT создаёт профиль", status == 200, str(player))
    check("имя сохранено", player.get("name") == "Smoke Tom", str(player))
    check("уровень сохранён", player.get("level") == 5, str(player))
    check("жизни сохранены", player.get("lives") == 2, str(player))
    check("карман сохранён", (player.get("drops"), player.get("keys")) == (4, 1), str(player))

    # 3. повторная запись: рекорд и визиты не уменьшаются
    status, player = request(
        "PUT",
        f"/api/players/{PLAYER_ID}",
        {
            "player_id": PLAYER_ID,
            "name": "Smoke Tom",
            "visits": 1,
            "level": 2,
            "max_level": 3,
            "lives": 3,
        },
    )
    check("повторный PUT обновляет", status == 200, str(player))
    check("max_level только растёт", player.get("max_level") == 7, str(player))
    check("visits не уменьшаются", player.get("visits") == 3, str(player))

    # 4. чтение + события
    status, player = request("GET", f"/api/players/{PLAYER_ID}")
    check("GET профиля", status == 200 and player.get("player_id") == PLAYER_ID, str(player))

    # 5. событие
    status, _ = request(
        "POST",
        f"/api/players/{PLAYER_ID}/events",
        {"kind": "level", "payload": {"level": 7, "mode": "classic"}},
    )
    check("POST события", status == 202, str(status))
    status, player = request("GET", f"/api/players/{PLAYER_ID}")
    events = player.get("events") or []
    check("событие в истории", any(e.get("kind") == "level" for e in events), str(events))

    # 6. лидерборд
    status, board = request("GET", "/api/players")
    check("лидерборд 200", status == 200, str(board))
    ids = [entry.get("player_id") for entry in board.get("entries", [])]
    check("игрок в лидерборде", PLAYER_ID in ids, str(ids))

    # 7. валидация
    status, _ = request(
        "PUT",
        "/api/players/bad",
        {"player_id": "bad", "level": 1},
    )
    check("некорректный player_id отклонён", status == 422, str(status))

    # 8. удаление
    status, _ = request("DELETE", f"/api/players/{PLAYER_ID}")
    check("DELETE 204", status == 204, str(status))
    status, _ = request("GET", f"/api/players/{PLAYER_ID}")
    check("после удаления 404", status == 404, str(status))

    auth_scenarios()

    print("Все проверки пройдены.")


def auth_scenarios() -> None:
    """Имя + пароль: регистрация, вход, ошибка пароля, уникальные PlayerN."""
    name = "authtest"
    other = "authtest2"
    cleanup(name, other)

    # 1. новое имя: пароль сохраняется вместе с именем
    status, result = request(
        "POST", "/api/auth/login", {"name": name, "password": "pass1234"}
    )
    check("регистрация нового имени", status == 200 and result.get("ok") is True, str(result))
    first_id = result.get("player_id")
    check("выдан player_id", bool(first_id), str(result))

    # после регистрации имя занято и защищено паролем
    status, info = request("POST", "/api/auth/check", {"name": name})
    check("имя занято", info.get("exists") is True, str(info))
    check("пароль требуется", info.get("has_password") is True, str(info))

    # 2. вход с верным паролем — тот же игрок
    status, result = request(
        "POST", "/api/auth/login", {"name": name, "password": "pass1234"}
    )
    check("вход с верным паролем", result.get("ok") is True, str(result))
    check("тот же игрок", result.get("player_id") == first_id, str(result))

    # 3. вход с неверным паролем — отказ, имя не меняется
    status, result = request(
        "POST", "/api/auth/login", {"name": name, "password": "wrongpass"}
    )
    check("неверный пароль отклонён", result.get("ok") is False, str(result))
    check("причина wrong_password", result.get("reason") == "wrong_password", str(result))

    # 4. вход с другого устройства (другой player_id) — выдаётся запись имени
    status, result = request(
        "POST",
        "/api/auth/login",
        {"name": name, "password": "pass1234", "player_id": "otherdevice01"},
    )
    check("вход с другого устройства", result.get("ok") is True, str(result))
    check("player_id записи сохранён", result.get("player_id") == first_id, str(result))

    # 5. короткий пароль — отказ валидации
    status, _ = request("POST", "/api/auth/login", {"name": other, "password": "ab"})
    check("короткий пароль отклонён", status == 422, str(status))

    # 6. default-имена уникальны: next-name не совпадает с занятыми PlayerN
    status, first = request("GET", "/api/auth/next-name")
    check("next-name получен", status == 200 and first.get("name", "").startswith("Player"), str(first))
    request("POST", "/api/auth/login", {"name": first["name"], "password": "pass1234"})
    status, second = request("GET", "/api/auth/next-name")
    check(
        "следующее имя отличается",
        second.get("name") != first.get("name"),
        f"{first} / {second}",
    )

    cleanup(name, other, first["name"], second.get("name", ""))


def cleanup(*names: str) -> None:
    """Удалить тестовые записи по именам."""
    for name in names:
        if not name:
            continue
        status, info = request("POST", "/api/auth/check", {"name": name})
        if not info.get("exists"):
            continue
        # профиль ищем по лидерборду: эндпоинта «поиск по имени» нет
        status, board = request("GET", "/api/players?limit=500")
        for entry in board.get("entries", []):
            if (entry.get("name") or "").lower() == name.lower():
                request("DELETE", f"/api/players/{entry['player_id']}")


if __name__ == "__main__":
    main()
