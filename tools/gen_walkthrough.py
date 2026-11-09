#!/usr/bin/env python3
"""Генерирует план прохождения классических уровней (режим classic).

Для каждого уровня из main/levels.json решатель tools/solve_level.py ищет
последовательность действий игрока, которая приводит шар к открытому и
достигнутому выходу, и минимальный набор предметов, который нужен на старте.
Скрипт оформляет результат в человекочитаемый Markdown:

  * карта уровня (платформы, объекты, перегородки);
  * сколько капель/ключей/молотков нужно иметь на старте и сколько тратится;
  * пошаговый план действий в понятных формулировках.

Координаты — экранные: row 0 — нижний ряд, col 0 — левая колонка
(в main/levels.json строки идут сверху вниз, здесь они уже перевёрнуты).

Использование:
    python3 tools/gen_walkthrough.py
    python3 tools/gen_walkthrough.py --out tools/LEVELS_WALKTHROUGH.md
    python3 tools/gen_walkthrough.py --only 1,2,48 --levels 1,2,48
    python3 tools/gen_walkthrough.py --node-cap 300000 --cache tools/_solutions.json
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bench_solve as bs  # noqa: E402  (общая формула сложности)
import level_interest as li  # noqa: E402
import solve_level as sv  # noqa: E402

DEFAULT_LEVELS = os.path.join(HERE, "..", "main", "levels.json")
DEFAULT_OUT = os.path.join(HERE, "LEVELS_WALKTHROUGH.md")

# формы слов по числу: (1, 2..4, 0 и 5..) — «1 капля / 2 капли / 5 капель»
RES_FORMS = {
    "drops": ("капля", "капли", "капель"),
    "keys": ("ключ", "ключа", "ключей"),
    "hammers": ("молоток", "молотка", "молотков"),
}


def plural(n, forms):
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return forms[1]
    return forms[2]

# --- карта ----------------------------------------------------------------

PLAT_CHARS = {
    0: ".",
    1: "=",   # обычная
    2: "3",   # shrinkable: 3 использования
    3: "2",   # shrinkable: 2 использования
    4: "1",   # shrinkable: 1 использование
    5: "~",   # липкая
    6: "<",   # наклон влево
    7: ">",   # наклон вправо
    8: "*",   # горящая
    9: "%",   # горящая + липкая
    10: "#",  # кирпичная кладка
    12: "^",  # шипы
}

OBJ_CHARS = {
    0: ".",
    1: "H",  # молоток
    2: "K",  # ключ
    3: "d",  # капля
    4: "L",  # жизнь
}

PLAT_LEGEND = [
    ("=", "обычная платформа"),
    ("3/2/1", "сжимающаяся: остаток использований"),
    ("~", "липкая"),
    ("</>", "наклонная (влево/вправо)"),
    ("*", "горящая (нужна капля или смерть)"),
    ("%", "горящая и липкая"),
    ("#", "кирпичная кладка (молоток)"),
    ("^", "шипы (смерть)"),
    (".", "пусто"),
]

OBJ_LEGEND = [
    ("H", "молоток"),
    ("K", "ключ"),
    ("d", "капля (гасит огонь)"),
    ("L", "жизнь"),
    ("o", "фрукт: открывает выход, когда собрано нужное число"),
    (".", "нет предмета"),
]

WALL_LEGEND = [
    ("3", "разрушаемая, 3 удара = 3 ключа"),
    ("2", "разрушаемая, 2 удара = 2 ключа"),
    ("1", "разрушаемая, 1 удар = 1 ключ"),
    ("4", "неразрушаемая (только обойти)"),
]


def plat_char(code):
    return PLAT_CHARS.get(code, "?")


def obj_char(code):
    if code >= 5:
        return "o"
    return OBJ_CHARS.get(code, "?")


def level_map(level):
    """Карта 6x6: две строки на ряд (платформы и объекты) сверху вниз."""
    lines = []
    for r in range(sv.ROWS - 1, -1, -1):
        cells = []
        for c in range(sv.COLS):
            cells.append(plat_char(level.plat[r][c]) + obj_char(level.obj[r][c]))
        lines.append(f"  ряд {r}  " + " ".join(cells))
    return "\n".join(lines)


def level_walls(level):
    rows = []
    for r in range(sv.ROWS - 1, -1, -1):
        parts = []
        for c in range(sv.COLS - 1):
            code = level.wall_code(r, c + 1)
            if code:
                parts.append(f"b{c + 1}={code}")
        if parts:
            rows.append(f"  ряд {r}: " + ", ".join(parts))
    return "\n".join(rows)


# --- действия -------------------------------------------------------------

HOP = re.compile(r"^hop \((\d+),(\d+)\) -> \((\d+),(\d+)\)$")
HOP_BACK = re.compile(r"^hop from \((\d+),(\d+)\) and return via column (\d+)$")
HOP_TO_COL = re.compile(r"^hop to column (\d+)$")
HJ_PLACE = re.compile(r"^high jump in place at \((\d+),(\d+)\)$")
HJ_DIVERT = re.compile(r"^high jump, divert to \((\d+),(\d+)\)$")
HJ_DIVERT_COL = re.compile(r"^high jump, divert to column (\d+)$")
HJ_WALL = re.compile(r"^high jump, break wall (\d+) at row (\d+) \((\d+) keys\)$")
WALL = re.compile(r"^break wall (\d+) at row (\d+) \((\d+) keys\)$")
BLOCK_BREAK = re.compile(
    r"^break block \((\d+),(\d+)\) from below(?: \(uses 1 hammer\))?$")
BLOCK_HIT = re.compile(
    r"^hit block \((\d+),(\d+)\) from below \((\d+)/\d+ rows(?:, uses 1 hammer)?\)$")
BOUNCE_WALL = re.compile(r"^bounce off wall (\d+) at row (\d+)$")
BOUNCE_BLOCK = re.compile(r"^bounce off block \((\d+),(\d+)\)$")

FATAL_SUFFIX = " (fatal)"
VANISH_FALL_OFF = ", platform vanishes and falls off"
VANISH_FALL = ", platform vanishes and falls"


def translate_core(label):
    """Метка действия без суффиксов -> фраза для игрока."""
    m = HOP.match(label)
    if m:
        r, c, r2, c2 = map(int, m.groups())
        return f"хоп ({r},{c}) → ({r2},{c2})"
    m = HOP_BACK.match(label)
    if m:
        r, c, c2 = map(int, m.groups())
        return f"хоп из ({r},{c}) назад через колонку {c2}"
    m = HOP_TO_COL.match(label)
    if m:
        return f"хоп в колонку {int(m.group(1))}"
    m = HJ_PLACE.match(label)
    if m:
        r, c = map(int, m.groups())
        return f"высокий прыжок на месте ({r},{c})"
    m = HJ_DIVERT.match(label)
    if m:
        r2, c2 = map(int, m.groups())
        return f"высокий прыжок с отводом в ({r2},{c2})"
    m = HJ_DIVERT_COL.match(label)
    if m:
        return f"высокий прыжок с отводом в колонку {int(m.group(1))}"
    m = HJ_WALL.match(label)
    if m:
        b, r, n = map(int, m.groups())
        return f"высокий прыжок с пробиванием перегородки b{b} в ряду {r} ({n} кл.)"
    m = WALL.match(label)
    if m:
        b, r, n = map(int, m.groups())
        return f"пробить перегородку b{b} в ряду {r} ({n} кл.)"
    m = BLOCK_BREAK.match(label)
    if m:
        r, c = map(int, m.groups())
        return f"разбить кладку ({r},{c}) снизу (молоток)"
    m = BLOCK_HIT.match(label)
    if m:
        r, c, done = map(int, m.groups())
        return f"ударить кладку ({r},{c}) снизу (выбито {done} ряд.)"
    m = BOUNCE_WALL.match(label)
    if m:
        b, r = map(int, m.groups())
        return f"отскок от перегородки b{b} в ряду {r}"
    m = BOUNCE_BLOCK.match(label)
    if m:
        r, c = map(int, m.groups())
        return f"отскок от кладки ({r},{c})"
    return label


def translate(label):
    """Метка действия решателя -> фраза для игрока (с суффиксами)."""
    core = label
    suffix = ""
    if core.endswith(VANISH_FALL_OFF):
        core = core[:-len(VANISH_FALL_OFF)]
        # платформа исчезла, шар ушёл за пределы поля — но выход уже открыт
        # и касание таблички засчитано (см. docstring solve_level.py)
        suffix = ("; платформа исчезает — шар падает за нижний край, "
                  "уровень засчитывается касанием выхода")
    elif core.endswith(VANISH_FALL):
        core = core[:-len(VANISH_FALL)]
        suffix = "; платформа исчезает — шар падает на поверхность ниже"
    fatal = core.endswith(FATAL_SUFFIX)
    if fatal:
        core = core[:-len(FATAL_SUFFIX)]
    text = translate_core(core)
    if fatal:
        text += " — в этом прыжке шар касается выхода (уровень завершён)"
    return text + suffix


def fmt_res(triple):
    parts = [f"{n} {plural(n, RES_FORMS[k])}"
             for n, k in zip(triple, ("drops", "keys", "hammers")) if n]
    return ", ".join(parts) if parts else "не нужно"


def solve_one(level, node_cap, allow_fallback=True):
    res = sv.solve(level, node_cap=node_cap, allow_fallback=allow_fallback)
    res.update(level=level.index, collectibles=level.collectibles, timer=level.timer,
               exit_cell=(level.exit_r, level.exit_c))
    return res


def render_level(level, res):
    out = []
    out.append(f"### Уровень {level.index}")
    out.append("")
    out.append(
        f"Старт: ({level.start_r},{level.start_c}) · выход: "
        f"({level.exit_r},{level.exit_c}) · для выхода нужно собрать фруктов: "
        f"{level.timer} (всего на карте {level.collectibles})")
    out.append("")
    status = res["status"]
    if status != "solvable":
        out.append(f"**Статус:** {status} — {res.get('reason') or 'план не найден'}")
        out.append("")
        return "\n".join(out)

    out.append(f"**Снаряжение на старте:** {fmt_res(res['required'])}")
    out.append("")
    out.append(f"**Потрачено по плану:** {fmt_res(res['used'])}")
    out.append("")
    note = "план проверен и минимален" if res.get("optimal") else \
        "план проверен, минимальность не доказана (лимит поиска)"
    out.append(f"**Действий:** {len(res['actions'])} · {note}")
    out.append("")
    out.append("```")
    out.append(level_map(level))
    walls = level_walls(level)
    out.append(walls if walls else "  перегородок нет")
    out.append("```")
    out.append("")
    out.append("План (row 0 — нижний ряд, col 0 — левая колонка):")
    out.append("")
    for i, label in enumerate(res["actions"], 1):
        out.append(f"{i}. {translate(label)}")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="План прохождения классических уровней.")
    ap.add_argument("levels", nargs="?", default=DEFAULT_LEVELS,
                    help="путь к levels.json (по умолчанию main/levels.json)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="путь к Markdown (по умолчанию tools/LEVELS_WALKTHROUGH.md)")
    ap.add_argument("--only", default=None,
                    help="список номеров уровней через запятую (например 1,2,48)")
    ap.add_argument("--node-cap", type=int, default=300000,
                    help="лимит узлов поиска на уровень")
    ap.add_argument("--cache", default=os.path.join(HERE, "_solutions.json"),
                    help="кэш решений (JSON); используется и обновляется")
    ap.add_argument("--no-cache", action="store_true",
                    help="не читать и не писать кэш")
    args = ap.parse_args()

    with open(args.levels, encoding="utf-8") as fh:
        model = json.load(fh)

    chosen = None
    if args.only:
        chosen = {int(x) for x in args.only.replace(" ", "").split(",") if x}

    cache = {}
    cache_path = None if args.no_cache else args.cache
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as fh:
                cache = json.load(fh)
        except (OSError, ValueError):
            cache = {}

    doc = []
    doc.append("# План прохождения уровней (режим classic)")
    doc.append("")
    doc.append("Документ генерируется [`tools/gen_walkthrough.py`](gen_walkthrough.py:1):")
    doc.append("каждый план найден решателем [`tools/solve_level.py`](solve_level.py:1) по")
    doc.append("метаданным [`main/levels.json`](../main/levels.json:1) и проверен его моделью")
    doc.append("правил (платформы, перегородки, кладка, огонь, шипы, липкие, наклоны,")
    doc.append("сжимающиеся платформы, открытие выхода).")
    doc.append("")
    doc.append("Координаты: `(row, col)`, где **row 0 — нижний ряд**, `col 0` — левая")
    doc.append("колонка. Перегородки нумеруются по границам: `b1` — между колонками 0 и 1,")
    doc.append("`b5` — между 4 и 5.")
    doc.append("")
    doc.append("«Снаряжение на старте» — минимум, который должен быть в кармане перед")
    doc.append("началом уровня (остальное можно подобрать по пути). Если этого нет, игра")
    doc.append("сразу завершается плашкой NOT ENOUGH THINGS (см.")
    doc.append("[`main/ball/ball_progress.lua`](../main/ball/ball_progress.lua:1)).")
    doc.append("")
    doc.append("## Как играть по плану")
    doc.append("")
    doc.append("| Шаг плана | Что делать в игре |")
    doc.append("|---|---|")
    doc.append("| хоп (r,c) → (r2,c2) | короткое нажатие прыжка в сторону нужной колонки |")
    doc.append("| высокий прыжок с отводом в (r2,c2) | удержать прыжок, в полёте нажать ячейку нужной колонки |")
    doc.append("| высокий прыжок на месте (r,c) | удержать прыжок, никуда не отводя |")
    doc.append("| пробить перегородку bN | прыгнуть в сторону перегородки (ключ тратится ударом) |")
    doc.append("| разбить кладку снизу | стоять под кладкой и жать прыжок (тратится молоток) |")
    doc.append("| отскок от перегородки/кладки | действие с сжимающейся платформы, шар остаётся на ней |")
    doc.append("")
    doc.append("Ключи и молотки тратятся автоматически при ударе; капля гасит горящую")
    doc.append("платформу при приземлении на неё. Фрукты собираются пролётом — отдельного")
    doc.append("действия не требуют.")
    doc.append("")
    doc.append("## Легенда карты")
    doc.append("")
    doc.append("Каждая ячейка карты — два символа: платформа и предмет в ней.")
    doc.append("")
    doc.append("| Символ | Платформа |")
    doc.append("|---|---|")
    for sym, name in PLAT_LEGEND:
        doc.append(f"| `{sym}` | {name} |")
    doc.append("")
    doc.append("| Символ | Предмет |")
    doc.append("|---|---|")
    for sym, name in OBJ_LEGEND:
        doc.append(f"| `{sym}` | {name} |")
    doc.append("")
    doc.append("| Код перегородки | Прочность |")
    doc.append("|---|---|")
    for sym, name in WALL_LEGEND:
        doc.append(f"| `{sym}` | {name} |")
    doc.append("")
    doc.append("## Сводка")
    doc.append("")
    doc.append("| Уровень | Действий | Стартовое снаряжение | Оптимальность |")
    doc.append("|---:|---:|---|---|")
    bodies = []
    solved = 0
    scores = []
    for data in model["levels"]:
        level = sv.Level(data)
        if chosen is not None and level.index not in chosen:
            continue
        key = str(level.index)
        res = None
        if cache_path and key in cache:
            cached = cache[key]
            if cached.get("node_cap", 0) >= args.node_cap:
                res = cached["result"]
        if res is None:
            res = solve_one(level, args.node_cap)
            if cache_path:
                cache[key] = {"node_cap": args.node_cap, "result": res}
            print(f"L{level.index:>3} {res['status']:<10} "
                  f"actions={len(res['actions']):<3} "
                  f"start=[{fmt_res(res['required'])}]", flush=True)
        else:
            print(f"L{level.index:>3} cached", flush=True)
        if res["status"] == "solvable":
            solved += 1
        bodies.append(render_level(level, res))
        opt = "да" if res.get("optimal") else ("—" if res["status"] != "solvable" else "не доказана")
        doc.append(f"| {level.index} | {len(res['actions'])} | "
                   f"{fmt_res(res['required'])} | {opt} |")
        # сложность по формуле бенчмарка (tools/bench_solve.py) и
        # «человеческая» интересность (tools/level_interest.py)
        feats = bs.features(sv, level, res, args.node_cap, 0.0)
        interest = li.analyze(level, res) if res["status"] == "solvable" else {}
        scores.append({
            "level": level.index,
            "features": feats,
            "difficulty": bs.difficulty(feats, args.node_cap),
            "band": bs.band(bs.difficulty(feats, args.node_cap)),
            "interest": interest,
        })

    doc.append("")
    doc.append(f"Всего уровней в плане: **{len(bodies)}**, планов найдено: **{solved}**.")
    doc.append("")
    doc.append("## Топ-10 по «человеческой» интересности")
    doc.append("")
    doc.append("Этот рейтинг ближе к ощущению игрока, чем статическая сложность:")
    doc.append("он взвешивает механику прохождения, а не количество объектов на карте")
    doc.append("([`tools/level_interest.py`](level_interest.py:1)):")
    doc.append("прицельные высокие прыжки с перестроением в полёте, необратимое")
    doc.append("обрушение пола, серии опор без отдыха, риск у обязательных фруктов,")
    doc.append("головоломки с кладкой и ловушки наклонов.")
    doc.append("")
    doc.append("| # | Уровень | Интересность | Точность | Необратимость | "
               "Без отдыха | Опасность у цели | Головоломка | Разнообразие |")
    doc.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    ranked_interest = sorted(
        (r for r in scores if r.get("interest")),
        key=lambda r: -r["interest"].get("interest", 0.0))
    for i, row in enumerate(ranked_interest[:10], 1):
        it = row["interest"]
        doc.append(
            f"| {i} | {row['level']} | {it.get('interest', 0.0)} | "
            f"{it.get('precision', 0.0):.0%} | "
            f"{it.get('irreversible', 0.0):.0%} | "
            f"{it.get('no_rest', 0.0):.0%} | "
            f"{it.get('hazard_goal', 0.0):.0%} | "
            f"{it.get('puzzle', 0.0):.0%} | "
            f"{it.get('variety', 0.0):.0%} |")
    doc.append("")
    doc.append("## Топ-10 по статической сложности")
    doc.append("")
    doc.append("Сложность считается формулой бенчмарка")
    doc.append("[`tools/bench_solve.py`](bench_solve.py:85): 0..100 — взвешенная сумма")
    doc.append("давления по снаряжению, плотности опасностей (шипы/огонь), препятствий")
    doc.append("(разрушаемые перегородки и кладка), нестабильных платформ (наклоны и")
    doc.append("сжимающиеся), усилий поиска решателя, длины маршрута и числа фруктов.")
    doc.append("")
    doc.append("| # | Уровень | Сложность | Класс | Действий | Снаряжение | "
               "Шипы+огонь | Стены+кладка | Наклоны+сжим. | Фруктов |")
    doc.append("|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|")
    bands_ru = {"easy": "простой", "medium": "средний",
                "hard": "сложный", "expert": "эксперт"}
    ranked = sorted(scores, key=lambda r: -r["difficulty"])
    for i, row in enumerate(ranked[:10], 1):
        f = row["features"]
        doc.append(
            f"| {i} | {row['level']} | {row['difficulty']} | "
            f"{bands_ru.get(row['band'], row['band'])} | {f['actions']} | "
            f"{f['required_sum']} | {f['spikes'] + f['burning']} | "
            f"{f['walls'] + f['blocks']} | {f['slopes'] + f['shrink']} | "
            f"{f['collectibles']} |")
    doc.append("")
    doc.append("Полный отчёт по сложности (сортируемый HTML) строит")
    doc.append("[`tools/bench_solve.py`](bench_solve.py:1) → `tools/levels_report.html`.")
    doc.append("")
    doc.append("## Пошаговые планы")
    doc.append("")
    doc.extend(bodies)

    text = "\n".join(doc).rstrip() + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)

    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)

    print()
    print(f"записано: {args.out}")
    print(f"уровней: {len(bodies)}, планов: {solved}")


if __name__ == "__main__":
    main()
