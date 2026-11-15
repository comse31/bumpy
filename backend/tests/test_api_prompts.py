"""Проверка HTTP-эндпоинтов промтов и оценок через TestClient FastAPI.

Запуск (из корня репозитория):
    python -m backend.tests.test_api_prompts

Тест поднимает приложение на временной БД и проходит сценарий игры:
  1. генератор присылает уровень БЕЗ промта — сервер собирает промт сам;
  2. GET /api/levels/random отдаёт уровень вместе с промтом;
  3. PUT /api/levels/{id}/prompt дозаполняет промт (бэкфилл);
  4. GET /api/levels/prompts/missing отдаёт уровни без промта, а после
     бэкфилла — пустой список;
  5. POST /api/levels/{id}/rating с verdict=down удаляет уровень из выдачи
     и появляется в GET /api/levels/negative-prompts;
  6. POST /api/levels/{id}/rating с verdict=up уровень не удаляет;
  7. некорректный verdict — 422, неизвестный уровень — 404.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# settings.py импортирует PyYAML на уровне модуля, а backend.app.main при
# импорте читает config.yml и создаёт БД. Тесту конфиг не нужен: он передаёт
# Settings явно. Поэтому, если PyYAML нет в окружении, подставляется заглушка,
# а путь config.yml уводится во временный каталог — файлы БД не должны
# появляться в репозитории.
_STUB_DIR = Path(tempfile.mkdtemp(prefix="bumpy-yaml-"))
_STUB_CONFIG = _STUB_DIR / "config.yml"
_STUB_CONFIG.write_text("""
database:
  path: '{db}'
  migrations_dir: '{migrations}'
api: {{}}
levels: {{}}
""".format(db=(_STUB_DIR / "stub.db").as_posix(),
           migrations=(ROOT / "backend" / "migrations").as_posix()),
    encoding="utf-8")
os.environ["BUMPY_CONFIG"] = str(_STUB_CONFIG)
if "yaml" not in sys.modules:  # pragma: no branch
    try:  # pragma: no cover - зависит от окружения
        import yaml  # noqa: F401
    except ModuleNotFoundError:  # pragma: no cover
        stub = types.ModuleType("yaml")
        stub.safe_load = lambda _fh=None: {  # noqa: ARG005
            "database": {
                "path": str(_STUB_DIR / "stub.db"),
                "migrations_dir": str(ROOT / "backend" / "migrations"),
            },
            "api": {},
            "levels": {},
        }
        sys.modules["yaml"] = stub

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import level_prompts  # noqa: E402
from backend.app.settings import (  # noqa: E402
    ApiSettings,
    DatabaseSettings,
    LevelsSettings,
    Settings,
)

LEVEL = {
    "level": 1,
    "grid_lo": [
        [0, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 1, 0],
        [0, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 0],
        [0, 1, 8, 1, 1, 5],
        [1, 1, 1, 1, 1, 0],
    ],
    "grid_hi": [[0] * 6 for _ in range(6)],
    "objects": [
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 5, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 2],
        [0, 0, 3, 0, 0, 0],
    ],
    "start_cell": 30,
    "timer": 1,
    "timer_cell": 5,
    "theme": 1,
}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        raise SystemExit(1)


def build_settings(tmpdir: Path) -> Settings:
    return Settings(
        database=DatabaseSettings(
            path=tmpdir / "bumpy.db",
            migrations_dir=ROOT / "backend" / "migrations",
        ),
        api=ApiSettings(),
        levels=LevelsSettings(),
        config_path=tmpdir / "config.yml",
    )


def payload(**extra) -> str:
    data = json.loads(json.dumps(LEVEL))
    data.update(extra)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    from backend.app.main import create_app  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        app = create_app(build_settings(tmpdir))
        client = TestClient(app)

        # 1. уровень без промта: сервер собирает его сам
        body = {
            "seed": 21,
            "level": 1,
            "payload": payload(),
            "status": "solvable",
            "drops": 1,
            "keys": 1,
            "hammers": 0,
            "generator": "test",
        }
        resp = client.post("/api/levels", json=body)
        check("POST /api/levels -> 201", resp.status_code == 201, resp.text)
        created = resp.json()
        check("промт собран сервером", bool(created.get("prompt")),
              str(created.get("prompt"))[:80])
        check("в промте есть требование",
              "1 капля" in created["prompt"] and "1 ключ" in created["prompt"])
        check("версия промта записана",
              created.get("prompt_version") == level_prompts.PROMPT_VERSION)
        level_id = created["level_id"]

        # 2. случайный уровень отдаётся вместе с промтом
        resp = client.get("/api/levels/random")
        check("GET /api/levels/random -> 200", resp.status_code == 200, resp.text)
        check("random отдаёт промт", bool(resp.json().get("prompt")))

        # 3. бэкфилл: стираем промт и дозаполняем через PUT
        with app.state.database.transaction() as conn:
            conn.execute("DELETE FROM level_prompts WHERE level_id = ?", (level_id,))

        resp = client.get("/api/levels/prompts/missing")
        check("GET /api/levels/prompts/missing -> 200", resp.status_code == 200)
        missing = resp.json()
        check("уровень без промта в списке",
              [item["level_id"] for item in missing] == [level_id], str(missing))
        check("в missing есть требования",
              missing[0]["drops"] == 1 and missing[0]["keys"] == 1)

        # промт строится с требованиями уровня: они лежат в колонках записи,
        # а не в payload, поэтому передаются явно
        prompt_source = dict(LEVEL, drops=1, keys=1, hammers=0)
        info = level_prompts.build(prompt_source)
        resp = client.put(
            f"/api/levels/{level_id}/prompt",
            json={
                "prompt": info["prompt"],
                "prompt_version": info["version"],
                "signature": json.dumps(info["signature"], ensure_ascii=False),
            },
        )
        check("PUT /api/levels/{id}/prompt -> 200", resp.status_code == 200, resp.text)
        check("промт обновлён", resp.json()["prompt"] == info["prompt"])
        resp = client.get("/api/levels/prompts/missing")
        check("после бэкфилла missing пуст", resp.json() == [])

        # 4. оценка «палец вниз»: уровень удаляется, появляется негативный пример
        resp = client.post(
            f"/api/levels/{level_id}/rating",
            json={"verdict": "down", "player_id": "p1234567890abcdef",
                  "classic_levels": 77},
        )
        check("POST rating down -> 200", resp.status_code == 200, resp.text)
        rated = resp.json()
        check("оценка принята", rated["ok"] is True and rated["verdict"] == "down")
        check("уровень удалён", rated["deleted"] is True)
        check("в ответе есть промт", rated["prompt"] == info["prompt"])

        resp = client.get("/api/levels/random")
        check("random больше не отдаёт удалённый уровень",
              resp.status_code == 404, resp.text)

        resp = client.get("/api/levels/negative-prompts")
        check("GET negative-prompts -> 200", resp.status_code == 200, resp.text)
        negatives = resp.json()
        check("негативный пример записан", len(negatives) == 1)
        check("в примере есть промт и подпись",
              bool(negatives[0]["prompt"]) and bool(negatives[0]["signature"]))
        check("в примере виден игрок",
              negatives[0]["player_id"] == "p1234567890abcdef")

        resp = client.get("/api/levels/stats")
        stats = resp.json()
        check("stats видит забракованный уровень", stats["rejected"] == 1)
        check("stats не видит уровней без промта", stats["without_prompt"] == 0)
        check("stats: уровней в БД не осталось", stats["total"] == 0)

        # 5. второй уровень: «палец вверх» его не удаляет
        body2 = dict(body, seed=22, payload=payload(theme=4))
        resp = client.post("/api/levels", json=body2)
        check("второй уровень сохранён", resp.status_code == 201, resp.text)
        level2 = resp.json()["level_id"]
        resp = client.post(
            f"/api/levels/{level2}/rating",
            json={"verdict": "up", "player_id": "p1234567890abcdef"},
        )
        check("POST rating up -> 200", resp.status_code == 200, resp.text)
        check("up не удаляет уровень", resp.json()["deleted"] is False)
        resp = client.get("/api/levels/random")
        check("уровень с up остаётся в выдаче", resp.status_code == 200, resp.text)
        check("оценка видна в ответе",
              resp.json().get("rating") == "up", str(resp.json().get("rating")))

        # 6. ошибки валидации
        resp = client.post(f"/api/levels/{level2}/rating",
                           json={"verdict": "maybe"})
        check("некорректный verdict -> 422", resp.status_code == 422, resp.text)
        resp = client.post("/api/levels/nonexistent/rating",
                           json={"verdict": "down"})
        check("неизвестный уровень -> 404", resp.status_code == 404, resp.text)
        resp = client.put("/api/levels/nonexistent/prompt",
                          json={"prompt": "x"})
        check("PUT промта неизвестному уровню -> 404",
              resp.status_code == 404, resp.text)
        resp = client.put(f"/api/levels/{level2}/prompt", json={"prompt": "   "})
        check("пустой промт -> 422", resp.status_code == 422, resp.text)

    print("HTTP-эндпоинты промтов и оценок: все проверки пройдены")


if __name__ == "__main__":
    main()
