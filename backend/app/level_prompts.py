"""Промт (правило генерации) для сгенерированного уровня Bumpy.

Зачем промт, если уровень полностью воспроизводится по seed:

  * seed воспроизводит уровень только этим генератором и этой его версией;
    промт описывает уровень в терминах правил игры, поэтому по нему уровень
    можно собрать заново — вручную, другим генератором или моделью;
  * промт нужен для обратной связи: если игрок поставил «палец вниз», уровень
    удаляется, а его промт становится отрицательным примером («так больше не
    генерировать»);
  * по промту видно, ЧТО именно было в уровне: состав платформ, требования,
    схема прохождения. Читать это по сырому payload в БД неудобно.

Модуль лежит в backend/app, потому что промт нужен обеим сторонам: генератору
(tools/gen_hourly.py) и серверу (POST /api/levels принимает уровень без промта
и собирает его сам, а tools/backfill_prompts.py дозаполняет старые записи).
Он не тянет ни fastapi, ни базу: на вход идёт payload уровня в формате
main/levels.json, на выходе — текст промта и компактная подпись (signature)
для поиска похожих уровней.

Использование:
    from backend.app import level_prompts
    info = level_prompts.build(level_payload, plan=actions)
    info["prompt"]     # текст правила
    info["signature"]  # dict с признаками
    info["version"]    # версия формата

    level_prompts.similarity(sig_a, sig_b)   # 0..1
    level_prompts.too_similar(sig, negatives, threshold=0.82)
"""

from __future__ import annotations

import json

# Версия формата промта. Меняется, когда меняется текст/структура: по ней
# tools/backfill_prompts.py и GET /api/levels/prompts/missing понимают, какие
# записи надо пересобрать.
#
# 2 — фрукты в подписи сведены к одному классу «collectible»: раньше каждый
# фрукт имел свой код, и два уровня с одинаковой механикой считались разными;
# 3 — в подпись добавлены профили поля и маска занятости: без них уровни с
# одинаковым набором платформ, но разной расстановкой считались похожими.
PROMPT_VERSION = 3

COLS = 6
ROWS = 6

# Названия кодов слоя lo (main/level/level.script: PLATFORM_BY_CODE).
PLATFORM_NAMES = {
    1: "обычная платформа",
    2: "сжимающаяся платформа (3 использования)",
    3: "сжимающаяся платформа (2 использования)",
    4: "сжимающаяся платформа (1 использование)",
    5: "липкая платформа",
    6: "наклонная платформа (влево)",
    7: "наклонная платформа (вправо)",
    8: "горящая платформа",
    9: "горящая липкая платформа",
    10: "кирпичная кладка",
    12: "шипы",
}

# Коды объектов (main/level/level.script: goodie_factory). Коды >= 5 —
# фрукты-коллектиблы, они отличаются только картинкой и для правил одинаковы.
OBJECT_NAMES = {
    1: "молоток",
    2: "ключ",
    3: "капля (гасит огонь)",
    4: "жизнь",
}
OBJECT_COLLECTIBLE = "фрукт"

# Названия кодов слоя hi: прочность перегородки = число ключей на удар.
WALL_NAMES = {
    1: "разрушаемая (1 ключ)",
    2: "разрушаемая (2 ключа)",
    3: "разрушаемая (3 ключа)",
    4: "неразрушаемая",
}

RES_FORMS = {
    "drops": ("капля", "капли", "капель"),
    "keys": ("ключ", "ключа", "ключей"),
    "hammers": ("молоток", "молотка", "молотков"),
}


def plural(n: int, forms: tuple[str, str, str]) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return forms[1]
    return forms[2]


def fmt_res(triple) -> str:
    """(drops, keys, hammers) -> «1 капля, 2 ключа» / «не требуется»."""
    parts = [
        f"{int(n)} {plural(int(n), RES_FORMS[key])}"
        for n, key in zip(triple, ("drops", "keys", "hammers"))
        if int(n)
    ]
    return ", ".join(parts) if parts else "не требуется"


def _screen_rc(cell: int) -> tuple[int, int]:
    """Индекс клетки метаданных (row 0 = верх) -> (row, col), row 0 = низ.

    В payload уровни хранятся сверху вниз (как в main/levels.json), а в
    промте и в плане прохождения удобнее экранная система: row 0 — нижний ряд.
    """
    return (ROWS - 1) - (cell // COLS), cell % COLS


def _plat_name(code: int) -> str:
    return PLATFORM_NAMES.get(code, f"код {code}")


def _obj_name(code: int) -> str:
    if code >= 5:
        return OBJECT_COLLECTIBLE
    return OBJECT_NAMES.get(code, f"код {code}")


# --- подпись уровня ----------------------------------------------------------


def _counts(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(int(value))
        out[key] = out.get(key, 0) + 1
    return out


def signature(level: dict, plan=None) -> dict:
    """Компактный вектор признаков уровня (JSON-совместимый).

    Подпись — не промт: она нужна только для сравнения уровней между собой.
    Поэтому здесь счётчики по кодам, требования и геометрия, а не текст.

    Кроме счётчиков по кодам в подпись входит профиль поля: сколько
    поверхностей в каждой колонке и в каждом ряду (row 0 — нижний). Счётчики
    по кодам почти не различают два уровня с одинаковым набором платформ, но
    разной их расстановкой, а профиль — различает: именно он не даёт считать
    «похожим» уровень, где платформы просто переставлены.
    """
    grid_lo = level.get("grid_lo") or []
    grid_hi = level.get("grid_hi") or []
    objects = level.get("objects") or []

    plat_flat = [int(v) for row in grid_lo for v in row]
    wall_flat = [int(v) for row in grid_hi for v in row]
    obj_flat = [int(v) for row in objects for v in row]

    # профиль поля: поверхности по колонкам и по рядам (экранные ряды)
    col_profile = [0] * COLS
    row_profile = [0] * ROWS
    # Маска занятости поля: 36 символов (0/1) в экранном порядке (row 0 —
    # нижний ряд). Именно она отличает уровень с той же статистикой, но другой
    # расстановкой поверхностей: счётчики по кодам такое различие не видят.
    occupancy = []
    for meta_row, row in enumerate(grid_lo):
        if not isinstance(row, list):
            continue
        for col, value in enumerate(row[:COLS]):
            if int(value):
                col_profile[col] += 1
                row_profile[ROWS - 1 - meta_row] += 1
    for row in range(ROWS - 1, -1, -1):
        meta_row = ROWS - 1 - row
        for col in range(COLS):
            try:
                code = int(grid_lo[meta_row][col])
            except (IndexError, TypeError, ValueError):
                code = 0
            occupancy.append("1" if code else "0")
    occupancy_mask = "".join(occupancy)

    start_cell = int(level.get("start_cell") or 0)
    exit_cell = int(level.get("timer_cell") or 0)
    start_r, start_c = _screen_rc(start_cell)
    exit_r, exit_c = _screen_rc(exit_cell)

    collectibles = sum(1 for v in obj_flat if v >= 5)
    # Все фрукты (коды >= 5) для правил одинаковы: они отличаются только
    # картинкой. В подписи они сводятся к одному классу, иначе два уровня с
    # одинаковой механикой, но разными фруктами считались бы разными.
    objects = _counts(v for v in obj_flat if 0 < v < 5)
    if collectibles:
        objects["collectible"] = collectibles
    return {
        "platforms": _counts(v for v in plat_flat if v),
        "walls": _counts(v for v in wall_flat if v),
        "objects": objects,
        "timer": int(level.get("timer") or 0),
        "collectibles": collectibles,
        "required": [
            int(level.get("drops") or 0),
            int(level.get("keys") or 0),
            int(level.get("hammers") or 0),
        ],
        "start": [start_r, start_c],
        "exit": [exit_r, exit_c],
        "theme": int(level.get("theme") or 0),
        "actions": len(plan) if plan else 0,
        # геометрия поля: распределение поверхностей по колонкам и рядам
        "col_profile": col_profile,
        "row_profile": row_profile,
        # маска занятости поля (36 символов 0/1, row 0 — нижний ряд)
        "occupancy": occupancy_mask,
    }


def _count_distance(a: dict[str, int], b: dict[str, int]) -> float:
    """Нормированное различие двух счётчиков (0 — совпадают, 1 — максимум)."""
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    diff = sum(abs(int(a.get(k, 0)) - int(b.get(k, 0))) for k in keys)
    total = sum(int(a.get(k, 0)) for k in keys) + sum(int(b.get(k, 0)) for k in keys)
    return 0.0 if total == 0 else min(1.0, diff / total)


def _profile_distance(a, b) -> float:
    """Различие профилей (списков) поля: 0 — совпадают, 1 — максимум."""
    if not a or not b:
        return 0.0
    diff = sum(abs(int(x) - int(y)) for x, y in zip(a, b))
    total = sum(int(x) for x in a) + sum(int(y) for y in b)
    return 0.0 if total == 0 else min(1.0, diff / total)


def _mask_distance(a, b) -> float:
    """Доля несовпавших клеток двух масок занятости (0..1)."""
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    if length == 0:
        return 0.0
    diff = sum(1 for i in range(length) if a[i] != b[i])
    diff += abs(len(a) - len(b))
    return min(1.0, diff / max(len(a), len(b)))


def similarity(sig_a: dict, sig_b: dict) -> float:
    """Похожесть двух подписей: 0 — разные, 1 — идентичные.

    Веса подобраны так, чтобы «похожесть» отражала ощущение игрока: важнее
    всего состав платформ и положение старта/выхода, а тема оформления почти
    не влияет.
    """
    if not sig_a or not sig_b:
        return 0.0

    def cell_dist(a, b) -> float:
        if not a or not b:
            return 0.0
        # манхэттенское расстояние на поле 6x6, нормированное на максимум
        return min(1.0, (abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))) / 10.0)

    def res_dist(a, b) -> float:
        left = [int(v) for v in (a or (0, 0, 0))]
        right = [int(v) for v in (b or (0, 0, 0))]
        return min(1.0, sum(abs(x - y) for x, y in zip(left, right)) / 6.0)

    parts = [
        (0.22, _count_distance(sig_a.get("platforms") or {}, sig_b.get("platforms") or {})),
        (0.10, _count_distance(sig_a.get("walls") or {}, sig_b.get("walls") or {})),
        (0.10, _count_distance(sig_a.get("objects") or {}, sig_b.get("objects") or {})),
        (0.10, cell_dist(sig_a.get("start"), sig_b.get("start"))),
        (0.08, cell_dist(sig_a.get("exit"), sig_b.get("exit"))),
        (0.07, min(1.0, abs(int(sig_a.get("timer") or 0) - int(sig_b.get("timer") or 0)) / 5.0)),
        (0.05, res_dist(sig_a.get("required"), sig_b.get("required"))),
        (0.05, min(1.0, abs(int(sig_a.get("actions") or 0) -
                            int(sig_b.get("actions") or 0)) / 12.0)),
        # Геометрия поля: распределение поверхностей по колонкам и рядам,
        # плюс маска занятости. Маска — главный признак: два уровня с
        # одинаковым набором платформ, но разной расстановкой, по счётчикам
        # почти неразличимы, а по маске отличаются на десятки процентов.
        (0.10, _profile_distance(sig_a.get("col_profile"), sig_b.get("col_profile"))),
        (0.08, _profile_distance(sig_a.get("row_profile"), sig_b.get("row_profile"))),
        (0.18, _mask_distance(sig_a.get("occupancy"), sig_b.get("occupancy"))),
    ]
    total_weight = sum(w for w, _ in parts)
    if total_weight <= 0:
        return 0.0
    distance = sum(w * d for w, d in parts) / total_weight
    return max(0.0, min(1.0, 1.0 - distance))


def too_similar(sig: dict, negatives, threshold: float = 0.82) -> tuple[bool, dict | None]:
    """Похож ли уровень на какой-нибудь отрицательный пример.

    `negatives` — итерируемое из подписей (dict) или JSON-строк. Возвращает
    (похож, виновная_подпись) — второй элемент нужен для лога генератора:
    по нему видно, на какой забракованный уровень похож кандидат.
    """
    best = None
    best_score = 0.0
    for item in negatives or ():
        other = load_signature(item)
        if not other:
            continue
        score = similarity(sig, other)
        if score > best_score:
            best_score = score
            best = other
    if best is not None and best_score >= threshold:
        return True, best
    return False, None


def load_signature(value) -> dict | None:
    """Подпись из JSON-строки (как она лежит в БД) или из dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


# --- текст промта -----------------------------------------------------------


# Метки действий решателя (tools/solve_level.py: successors). Формулировки
# совпадают с планом прохождения (tools/gen_walkthrough.py: translate), но
# продублированы здесь: backend не должен зависеть от tools (в docker-образ
# копируется только backend/app).
_ACTION_PATTERNS = (
    (r"^hop \((\d+),(\d+)\) -> \((\d+),(\d+)\)", "хоп ({0},{1}) → ({2},{3})"),
    (r"^hop from \((\d+),(\d+)\) and return via column (\d+)",
     "хоп из ({0},{1}) назад через колонку {2}"),
    (r"^hop to column (\d+)", "хоп в колонку {0}"),
    (r"^high jump in place at \((\d+),(\d+)\)", "высокий прыжок на месте ({0},{1})"),
    (r"^high jump, divert to \((\d+),(\d+)\)", "высокий прыжок с отводом в ({0},{1})"),
    (r"^high jump, divert to column (\d+)", "высокий прыжок с отводом в колонку {0}"),
    (r"^high jump, break wall (\d+) at row (\d+) \((\d+) keys\)",
     "высокий прыжок с пробиванием перегородки b{0} в ряду {1} ({2} кл.)"),
    (r"^break wall (\d+) at row (\d+) \((\d+) keys\)",
     "пробить перегородку b{0} в ряду {1} ({2} кл.)"),
    (r"^break block \((\d+),(\d+)\) from below(?: \(uses 1 hammer\))?",
     "разбить кладку ({0},{1}) снизу (молоток)"),
    (r"^hit block \((\d+),(\d+)\) from below \((\d+)/\d+ rows(?:, uses 1 hammer)?\)",
     "ударить кладку ({0},{1}) снизу (выбито {2} ряд.)"),
    (r"^bounce off wall (\d+) at row (\d+)", "отскок от перегородки b{0} в ряду {1}"),
    (r"^bounce off block \((\d+),(\d+)\)", "отскок от кладки ({0},{1})"),
)

# Суффиксы, которые решатель добавляет к метке действия.
_FATAL_SUFFIX = " (fatal)"
_VANISH_FALL_OFF = ", platform vanishes and falls off"
_VANISH_FALL = ", platform vanishes and falls"


def _describe_action(label: str) -> str:
    """Метка действия решателя -> фраза для человека.

    Если метка не распознана, возвращается как есть: промт всё равно остаётся
    читаемым, а неожиданная формулировка решателя видна глазами.
    """
    import re  # noqa: PLC0415 - нужен только здесь

    core = label
    suffix = ""
    if core.endswith(_VANISH_FALL_OFF):
        core = core[: -len(_VANISH_FALL_OFF)]
        suffix = ("; платформа исчезает — шар падает за нижний край, "
                  "уровень засчитывается касанием выхода")
    elif core.endswith(_VANISH_FALL):
        core = core[: -len(_VANISH_FALL)]
        suffix = "; платформа исчезает — шар падает на поверхность ниже"
    fatal = core.endswith(_FATAL_SUFFIX)
    if fatal:
        core = core[: -len(_FATAL_SUFFIX)]

    text = core
    for pattern, template in _ACTION_PATTERNS:
        match = re.match(pattern, core)
        if match:
            text = template.format(*match.groups())
            break
    if fatal:
        text += " — в этом прыжке шар касается выхода (уровень завершён)"
    return text + suffix


def _map_lines(level: dict) -> list[str]:
    """Карта поля: по строке на ряд, row 0 — нижний."""
    grid_lo = level.get("grid_lo") or []
    objects = level.get("objects") or []
    start_r, start_c = _screen_rc(int(level.get("start_cell") or 0))
    exit_r, exit_c = _screen_rc(int(level.get("timer_cell") or 0))
    lines = []
    for row in range(ROWS - 1, -1, -1):
        meta_row = ROWS - 1 - row
        cells = []
        for col in range(COLS):
            lo = int(grid_lo[meta_row][col]) if meta_row < len(grid_lo) else 0
            obj = int(objects[meta_row][col]) if meta_row < len(objects) else 0
            if (row, col) == (start_r, start_c):
                cells.append("S")
            elif (row, col) == (exit_r, exit_c):
                cells.append("X")
            elif lo == 12:
                cells.append("^")
            elif lo == 10:
                cells.append("#")
            elif lo == 8 or lo == 9:
                cells.append("*")
            elif lo == 5:
                cells.append("~")
            elif lo in (6, 7):
                cells.append("<" if lo == 6 else ">")
            elif lo in (2, 3, 4):
                cells.append(str(6 - lo))  # остаток использований: 3/2/1
            elif lo:
                cells.append("=")
            elif obj:
                cells.append("o")
            else:
                cells.append(".")
        lines.append(f"  ряд {row}: " + " ".join(cells))
    return lines


def build(level: dict, *, plan=None, generator: str | None = None) -> dict:
    """Собрать промт и подпись для уровня.

    level — payload в формате main/levels.json (плюс необязательные drops/keys/
    hammers); plan — список действий решателя (tools/solve_level.py), если он
    известен. Возвращает dict: prompt, signature, version.
    """
    start_r, start_c = _screen_rc(int(level.get("start_cell") or 0))
    exit_r, exit_c = _screen_rc(int(level.get("timer_cell") or 0))
    grid_lo = level.get("grid_lo") or []
    grid_hi = level.get("grid_hi") or []
    objects = level.get("objects") or []
    timer = int(level.get("timer") or 0)

    out: list[str] = []
    out.append("Правило генерации уровня Bumpy (поле 6x6, шар-прыгун).")
    if generator:
        out.append(f"Источник: {generator}.")
    out.append("")
    out.append(
        f"Цель: собрать {timer} {plural(timer, ('фрукт', 'фрукта', 'фруктов'))} "
        f"и коснуться таблички выхода в клетке ({exit_r},{exit_c})."
    )
    out.append(f"Старт: клетка ({start_r},{start_c}).")
    out.append(
        "Снаряжение на старте: "
        + fmt_res((
            int(level.get("drops") or 0),
            int(level.get("keys") or 0),
            int(level.get("hammers") or 0),
        ))
        + "."
    )
    out.append("Координаты: (row, col), row 0 — нижний ряд, col 0 — левая колонка.")
    out.append("")

    # платформы
    platforms_by_code: dict[int, list[str]] = {}
    for meta_row in range(len(grid_lo)):
        for col in range(len(grid_lo[meta_row])):
            code = int(grid_lo[meta_row][col])
            if not code:
                continue
            row = ROWS - 1 - meta_row
            platforms_by_code.setdefault(code, []).append(f"({row},{col})")
    out.append("Платформы:")
    if not platforms_by_code:
        out.append("  (нет)")
    for code in sorted(platforms_by_code):
        cells = platforms_by_code[code]
        out.append(f"  - {_plat_name(code)}: {', '.join(cells)}")
    out.append("")

    # перегородки
    walls: list[str] = []
    for meta_row in range(len(grid_hi)):
        for col in range(len(grid_hi[meta_row]) - 1):
            code = int(grid_hi[meta_row][col])
            if not code:
                continue
            row = ROWS - 1 - meta_row
            walls.append(f"b{col + 1} в ряду {row} — {WALL_NAMES.get(code, f'код {code}')}")
    out.append("Перегородки:")
    out.extend(f"  - {w}" for w in walls) if walls else out.append("  (нет)")
    out.append("")

    # предметы
    items: list[str] = []
    for meta_row in range(len(objects)):
        for col in range(len(objects[meta_row])):
            code = int(objects[meta_row][col])
            if not code:
                continue
            row = ROWS - 1 - meta_row
            items.append(f"({row},{col}) {_obj_name(code)}")
    out.append("Предметы на поле:")
    out.extend(f"  - {item}" for item in items) if items else out.append("  (нет)")
    out.append("")

    # карта
    out.append("Карта (S — старт, X — выход, = обычная, ^ шипы, # кладка, "
               "* огонь, ~ липкая, </> наклон, 3/2/1 сжимающаяся, o предмет):")
    out.extend(_map_lines(level))
    out.append("")

    # схема прохождения
    if plan:
        out.append(f"Схема прохождения ({len(plan)} действий):")
        for i, label in enumerate(plan, 1):
            out.append(f"  {i}. {_describe_action(str(label))}")
        out.append("")

    out.append("Обязательные правила:")
    out.append("  - шар не начинает уровень на шипах или на огне (мгновенная смерть);")
    out.append("  - над кирпичной кладкой нет платформ: только кладка столбиком, "
               "иначе кладку нельзя разбить снизу;")
    out.append("  - уровень требует хотя бы один предмет на старте "
               "(капля/ключ/молоток), иначе он слишком простой;")
    out.append("  - перегородка ломается ключами, кладка — молотком, огонь — каплей;")
    out.append("  - уровень обязан быть проходим: проходимость подтверждается решателем.")

    return {
        "prompt": "\n".join(out).strip() + "\n",
        "signature": signature(level, plan=plan),
        "version": PROMPT_VERSION,
    }


def main() -> None:  # pragma: no cover - утилитарный запуск
    """Напечатать промт для уровня из файла (для отладки)."""
    import argparse

    ap = argparse.ArgumentParser(description="Промт для уровня Bumpy.")
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
