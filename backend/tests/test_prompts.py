"""Тест промтов уровней и обратной связи (палец вверх / палец вниз).

Запуск (из корня репозитория):
    python -m backend.tests.test_prompts

Тест не требует pytest и поднятого сервера: он работает с временной БД и
вызывает репозитории напрямую, поэтому проверяет именно логику:
  1. уровень сохраняется вместе с промтом (генератор прислал промт);
  2. уровень без промта от генератора получает промт на сервере;
  3. старый уровень без промта попадает в «missing» и дозаполняется upsert;
  4. «палец вниз» удаляет уровень из выдачи, но оставляет отрицательный
     пример с промтом и подписью;
  5. «палец вверх» уровень не удаляет;
  6. подпись забракованного уровня отдаётся генератору и распознаёт копию.
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# settings.py импортирует PyYAML на уровне модуля (он нужен только для чтения
# config.yml). Тесту достаточно dataclass DatabaseSettings, поэтому при
# отсутствии PyYAML подставляется пустая заглушка: тест не должен требовать
# установки зависимостей сервера.
try:  # pragma: no cover - зависит от окружения
    import yaml  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    sys.modules.setdefault("yaml", types.ModuleType("yaml"))

from backend.app import level_prompts  # noqa: E402
from backend.app.db import Database  # noqa: E402
from backend.app.levels_repository import GeneratedLevelRepository  # noqa: E402
from backend.app.settings import DatabaseSettings  # noqa: E402


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
    "grid_hi": [
        [0, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
    ],
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


def _payload(**extra) -> str:
    data = dict(LEVEL)
    data.update(extra)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _repo(tmp: Path) -> GeneratedLevelRepository:
    settings = DatabaseSettings(path=tmp, migrations_dir=ROOT / "backend" / "migrations")
    db = Database(settings)
    db.init()
    return GeneratedLevelRepository(db)


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        raise SystemExit(1)


def main() -> None:
    from backend.app.schemas import GeneratedLevelIn

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _repo(Path(tmpdir) / "bumpy.db")

        # 1. уровень с готовым промтом от генератора
        info = level_prompts.build(LEVEL)
        signature = json.dumps(info["signature"], ensure_ascii=False)
        saved = repo.add(GeneratedLevelIn(
            seed=11, level=1, payload=_payload(),
            drops=1, keys=1, hammers=1,
            prompt=info["prompt"], prompt_version=info["version"],
            signature=signature,
        ))
        check("промт сохранён вместе с уровнем",
              saved.prompt == info["prompt"], str(saved.prompt)[:80])
        check("версия промта сохранена",
              saved.prompt_version == level_prompts.PROMPT_VERSION)
        check("подпись сохранена",
              repo.prompts.get(saved.level_id).get("signature") is not None)

        # 2. уровень без промта: сервер собирает его сам
        plain = repo.add(GeneratedLevelIn(
            seed=12, level=1, payload=_payload(theme=3),
            drops=1, keys=0, hammers=0,
        ))
        check("промт собран сервером", bool(plain.prompt), str(plain.prompt)[:80])
        check("собранный промт содержит требование",
              "1 капля" in (plain.prompt or ""))

        # 3. бэкфилл: уровень без промта виден в missing и дозаполняется
        with repo.db.transaction() as conn:
            conn.execute(
                "DELETE FROM level_prompts WHERE level_id = ?", (plain.level_id,))
        check("уровень без промта попадает в missing",
              any(item["level_id"] == plain.level_id
                  for item in repo.prompts.missing()))
        check("count_missing считает такие уровни",
              repo.prompts.count_missing() == 1)
        repo.prompts.upsert(plain.level_id, "test prompt",
                            prompt_version=level_prompts.PROMPT_VERSION,
                            signature=signature)
        check("upsert записывает промт",
              repo.prompts.get(plain.level_id)["prompt"] == "test prompt")
        check("после upsert missing пуст", repo.prompts.count_missing() == 0)

        # 4. палец вниз: уровень удаляется, отрицательный пример остаётся
        before = repo.count()
        result = repo.prompts.rate(saved.level_id, "down",
                                   player_id="p1234567890abcdef")
        check("оценка down принята", result["rating"] == "down")
        check("оценка down удаляет уровень", result["deleted"] is True)
        check("уровень исчез из БД", repo.count() == before - 1)
        check("get() больше не находит уровень",
              repo.get(saved.level_id) is None)
        negatives = repo.prompts.negatives()
        check("отрицательный пример сохранён", len(negatives) == 1)
        check("в примере есть промт", negatives[0].prompt == info["prompt"])
        check("в примере есть подпись", bool(negatives[0].signature))
        check("stats видит забракованный уровень", repo.stats().rejected == 1)

        # 5. палец вверх: уровень остаётся
        up = repo.prompts.rate(plain.level_id, "up", player_id="p1234567890abcdef")
        check("оценка up не удаляет уровень", up["deleted"] is False)
        check("уровень на месте", repo.get(plain.level_id) is not None)
        check("повторная оценка видна истории",
              repo.prompts.has_rating(plain.level_id, "p1234567890abcdef"))

        # 6. отрицательный пример отсекает похожий уровень
        same = level_prompts.build(LEVEL)
        similar, culprit = level_prompts.too_similar(
            same["signature"], [negatives[0].signature], threshold=0.82)
        check("копия забракованного уровня отсекается", similar is True)
        check("виновник определён", culprit is not None)

        # другой уровень: иная геометрия платформ и другой набор предметов
        other_level = json.loads(_payload())
        other_level["grid_lo"] = [
            [1, 1, 0, 0, 1, 1],
            [0, 1, 1, 0, 1, 1],
            [1, 0, 1, 1, 0, 1],
            [1, 1, 0, 1, 1, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 1, 1, 1],
        ]
        other_level["objects"] = [
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ]
        other = level_prompts.build(other_level)
        similar2, _ = level_prompts.too_similar(
            other["signature"], [negatives[0].signature], threshold=0.82)
        check("другой уровень не отсекается", similar2 is False)

        # выдача случайного уровня не падает после удаления
        check("random() работает после удаления", repo.random() is not None)
        check("latest() отдаёт промт",
              all(item.prompt for item in repo.latest()))

    print("промты и оценки: все проверки пройдены")


if __name__ == "__main__":
    main()
