#!/usr/bin/env python3
"""«Человеческая» сложность уровня — то, что игрок чувствует руками.

Формула сложности в tools/bench_solve.py взвешивает статические плотности
(сколько шипов, перегородок и фруктов на карте). Игрок же оценивает уровень по
механике прохождения. Этот модуль считает именно её:

  * **precision** — доля высоких прыжков, требующих перестроения в полёте
    (тап по ячейке). Ошибка здесь не отменяется, а переигрывается;
  * **irreversible** — доля ходов, после которых платформа под шаром исчезает:
    вернуться уже нельзя;
  * **no_rest** — длина самой длинной серии ходов подряд без безопасной опоры
    (липкая, наклонная, сжимающаяся, горящая): непрерывное напряжение;
  * **forced_motion** — доля ходов, в которых шар двигается не по решению
    игрока, а из-за наклона/липкой платформы;
  * **hazard_goal** — доля ОБЯЗАТЕЛЬНЫХ фруктов, которые нельзя взять без
    риска: фрукт лежит на шипах/огне или висит прямо над ними;
  * **puzzle** — препятствия (кладка, перегородки) против стартового
    снаряжения: это чтение карты, а не реакция;
  * **trap_risk** — наклоны, сбрасывающие шар в край поля или в неразрушаемую
    перегородку (в игре это плашка YOU ARE TRAPPED и потеря жизни);
  * **variety** — сколько разных механик реально задействовано в плане:
    однообразный уровень быстро надоедает.

Модуль зависит только от solve_level: на вход идёт `solve_level.Level` и
результат `solve_level.solve()` (план действий). Поэтому он используется и
генератором уровней, и отчётами.

Важно: «человеческий» балл НЕ заменяет доказательство проходимости. Уровень
сначала проверяется решателем, и только потом оценивается по интересности.

Использование:
    import level_interest as li
    score = li.analyze(level, res)
    score["interest"]   # 0..100
    li.describe(score)  # строка для лога
"""

from __future__ import annotations

import re

# Коды платформ (main/level/level.script: PLATFORM_BY_CODE)
LO_EMPTY = 0
LO_DEFAULT = 1
LO_SHRINK = 2
LO_SHRINK_WORN = 3
LO_SHRINK_WORN2 = 4
LO_STICKY = 5
LO_SLOPE_LEFT = 6
LO_SLOPE_RIGHT = 7
LO_BURNING = 8
LO_BURNING_STICKY = 9
LO_BLOCK = 10
LO_SPIKE = 12

# Поверхности, на которых шар может стоять спокойно и бесконечно.
SAFE_SUPPORT = frozenset({LO_DEFAULT, LO_BLOCK})
# Поверхности, которые расходуются или сбрасывают шар без выбора игрока.
UNSTABLE_SUPPORT = frozenset({
    LO_SHRINK, LO_SHRINK_WORN, LO_SHRINK_WORN2,   # сжимающиеся
    LO_STICKY,                                   # липкая
    LO_SLOPE_LEFT, LO_SLOPE_RIGHT,               # наклонные
    LO_BURNING, LO_BURNING_STICKY,               # горящие
})
# Опасные поверхности: приземление стоит жизни (шипы) или капли (огонь).
HAZARD_SUPPORT = frozenset({LO_SPIKE, LO_BURNING, LO_BURNING_STICKY})

_COLS = 6
_ROWS = 6

# Веса компонентов «человеческой» интересности (сумма = 1.0). Значения
# подобраны так, чтобы рейтинг совпадал с ощущением игрока: уровни с
# прицельными прыжками над шипами и с обрушением пола оказываются выше
# «длинных, но однообразных».
WEIGHTS = {
    "precision": 0.18,
    "irreversible": 0.13,
    "no_rest": 0.10,
    "forced_motion": 0.07,
    "hazard_goal": 0.13,
    "puzzle": 0.09,
    "trap_risk": 0.06,
    "variety": 0.07,
    # структурные признаки: уровень может быть коротким, но «ребусным» или
    # стоящим целиком на одноразовом поле
    "maze": 0.09,
    "oneshot_field": 0.08,
}

# сколько кладок в поле считаем «полным ребусом» (уровень 93 — 24 кладки)
MAZE_FULL = 12
# сколько клеток поля должно быть одноразовыми для полного балла
ONESHOT_FIELD_FULL = 36

# Сколько разных механик считаем «полным набором» для variety.
VARIETY_FULL = 8

# Метки действий решателя (см. tools/solve_level.py: successors).
_HOP = re.compile(r"^hop \((\d+),(\d+)\) -> \((\d+),(\d+)\)")
_HOP_BACK = re.compile(r"^hop from \((\d+),(\d+)\) and return via column (\d+)")
_HOP_FATAL = re.compile(r"^hop to column (\d+)")
_HJ_PLACE = re.compile(r"^high jump in place at \((\d+),(\d+)\)")
_HJ_DIVERT = re.compile(r"^high jump, divert to \((\d+),(\d+)\)")
_HJ_DIVERT_COL = re.compile(r"^high jump, divert to column (\d+)")
_HJ_WALL = re.compile(r"^high jump, break wall (\d+) at row (\d+)")
_WALL = re.compile(r"^break wall (\d+) at row (\d+)")
_BLOCK = re.compile(r"^(?:break|hit) block \((\d+),(\d+)\)")
_BOUNCE = re.compile(r"^bounce off (wall|block)")


def plat_at(level, row: int, col: int) -> int:
    if 0 <= row < _ROWS and 0 <= col < _COLS:
        return level.plat[row][col]
    return LO_EMPTY


def support_cells(actions) -> list[tuple[int, int]]:
    """Клетки, на которых шар стоит перед каждым действием плана."""
    cells: list[tuple[int, int]] = []
    for label in actions:
        m = _HOP.match(label) or _HOP_BACK.match(label) or _HJ_PLACE.match(label)
        if m:
            cells.append((int(m.group(1)), int(m.group(2))))
    return cells


def action_kinds(actions) -> dict[str, int]:
    """Разбор плана по типам действий."""
    kinds = {
        "hop": 0, "hop_back": 0, "hop_fatal": 0,
        "hj_place": 0, "hj_divert": 0, "hj_wall": 0,
        "wall": 0, "block": 0, "bounce": 0,
        "vanish": 0, "fatal": 0, "total": 0,
    }
    for label in actions:
        kinds["total"] += 1
        if "vanishes" in label:
            kinds["vanish"] += 1
        if "(fatal)" in label:
            kinds["fatal"] += 1
        if _HOP.match(label):
            kinds["hop"] += 1
        elif _HOP_BACK.match(label):
            kinds["hop_back"] += 1
        elif _HOP_FATAL.match(label):
            kinds["hop_fatal"] += 1
        elif _HJ_PLACE.match(label):
            kinds["hj_place"] += 1
        elif _HJ_DIVERT.match(label) or _HJ_DIVERT_COL.match(label):
            kinds["hj_divert"] += 1
        elif _HJ_WALL.match(label):
            kinds["hj_wall"] += 1
            kinds["wall"] += 1
        elif _WALL.match(label):
            kinds["wall"] += 1
        elif _BLOCK.match(label):
            kinds["block"] += 1
        elif _BOUNCE.match(label):
            kinds["bounce"] += 1
    return kinds


def slope_traps(level) -> list[tuple[int, int]]:
    """Наклоны, сбрасывающие шар в край поля или в неразрушаемую перегородку.

    Такой наклон не «переносит» шар, а запирает его: в игре это ловушка
    (main/ball/ball_trap.lua → плашка YOU ARE TRAPPED и потеря жизни).
    """
    traps = []
    for r in range(_ROWS):
        for c in range(_COLS):
            code = level.plat[r][c]
            if code not in (LO_SLOPE_LEFT, LO_SLOPE_RIGHT):
                continue
            direction = -1 if code == LO_SLOPE_LEFT else 1
            c2 = c + direction
            if not (0 <= c2 < _COLS):
                traps.append((r, c))
                continue
            if level.wall_code(r, max(c, c2)) == 4:  # HI_WALL_SOLID
                traps.append((r, c))
    return traps


def hazard_goals(level) -> dict:
    """Фрукты, которые нельзя собрать без риска.

    Фрукт рискован, если он лежит на опасной клетке (шипы/огонь) ЛИБО его
    приходится брать над опасностью: ближайшая поверхность под ним в той же
    колонке — шипы или огонь. Второй случай — это «висящие над шипами» фрукты
    уровней 61/92/75: сама опора безопасна, но промах на подлёте смертелен.
    """
    total = 0
    on_hazard = 0
    above_hazard = 0
    risky = 0
    for r in range(_ROWS):
        for c in range(_COLS):
            if level.obj[r][c] < 5:
                continue
            total += 1
            own = plat_at(level, r, c) in HAZARD_SUPPORT
            below = None
            for rr in range(r - 1, -1, -1):
                code = plat_at(level, rr, c)
                if code != LO_EMPTY:
                    below = code
                    break
            near = below in HAZARD_SUPPORT
            if own:
                on_hazard += 1
            if near and not own:
                above_hazard += 1
            if own or near:
                risky += 1
    return {
        "fruits": total,
        "on_hazard": on_hazard,
        "above_hazard": above_hazard,
        "risky": risky,
        # все фрукты обязательны, если выход требует собрать их все
        "must_collect_all": total > 0 and level.timer >= total,
        "share": (risky / total) if total else 0.0,
    }


def longest_unstable_run(level, cells) -> int:
    """Самая длинная серия ходов подряд на нестабильных опорах.

    Одна липкая платформа — один точный тайминг. Шесть подряд — непрерывное
    напряжение, где нельзя ни остановиться, ни передохнуть.
    """
    best = run = 0
    for r, c in cells:
        if plat_at(level, r, c) in UNSTABLE_SUPPORT:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def variety_of(level, kinds) -> int:
    """Сколько разных механик задействовано в плане и на карте."""
    used = set()
    if kinds["hop"]:
        used.add("hop")
    if kinds["hj_place"] or kinds["hj_divert"] or kinds["hj_wall"]:
        used.add("high_jump")
    if kinds["wall"]:
        used.add("wall")
    if kinds["block"]:
        used.add("block")
    if kinds["vanish"]:
        used.add("vanishing_floor")
    if kinds["bounce"] or kinds["hop_back"]:
        used.add("forced_motion")
    for r in range(_ROWS):
        for c in range(_COLS):
            code = level.plat[r][c]
            if code in (LO_SLOPE_LEFT, LO_SLOPE_RIGHT):
                used.add("slope")
            elif code == LO_STICKY:
                used.add("sticky")
            elif code in (LO_SHRINK, LO_SHRINK_WORN, LO_SHRINK_WORN2):
                used.add("shrink")
            elif code in (LO_BURNING, LO_BURNING_STICKY):
                used.add("burning")
            elif code == LO_SPIKE:
                used.add("spike")
    return len(used)


def analyze(level, res: dict) -> dict:
    """Компоненты «человеческой» сложности и итоговый балл 0..100.

    `level` — solve_level.Level, `res` — результат solve() с полем actions.
    """
    actions = res.get("actions") or []
    kinds = action_kinds(actions)
    total = max(1, kinds["total"])
    cells = support_cells(actions)

    # 1. точность: доля высоких прыжков с перестроением в полёте
    high_jumps = kinds["hj_place"] + kinds["hj_divert"] + kinds["hj_wall"]
    precision = (kinds["hj_divert"] / high_jumps) if high_jumps else 0.0

    # 2. необратимость: доля ходов, после которых пол исчезает
    irreversible = kinds["vanish"] / total

    # 3. нет отдыха: длина серии без безопасной опоры (нормируем на 6 ходов)
    run = longest_unstable_run(level, cells)
    no_rest = min(1.0, run / 6.0)

    # 4. вынужденное движение: шар сносит наклоном/липкой без решения игрока
    forced = (kinds["hop_back"] + kinds["bounce"]) / total

    # 5. опасность у цели: фрукты, которые нельзя взять без риска
    goals = hazard_goals(level)
    hazard_goal = goals["share"]
    if not goals["must_collect_all"]:
        # часть фруктов можно пропустить — риск необязателен
        hazard_goal *= 0.6

    # 6. головоломка: препятствия против стартового снаряжения
    req = res.get("required") or (0, 0, 0)
    obstacles = kinds["wall"] + kinds["block"]
    if obstacles:
        # мало инструментов при многих препятствиях = чтение карты
        tool_ratio = min(1.0, sum(req) / obstacles)
        puzzle = min(1.0, obstacles / 8.0) * (0.4 + 0.6 * tool_ratio)
    else:
        puzzle = 0.0

    # 7. риск ловушки: доля наклонов, сбрасывающих шар в край/стену
    traps = slope_traps(level)
    slopes = sum(1 for r in range(_ROWS) for c in range(_COLS)
                 if level.plat[r][c] in (LO_SLOPE_LEFT, LO_SLOPE_RIGHT))
    trap_risk = min(1.0, len(traps) / slopes) if slopes else 0.0

    # 8. разнообразие механик
    variety = min(1.0, variety_of(level, kinds) / VARIETY_FULL)

    # 9. ребус: сколько поля заложено кирпичом. Уровень 93 — 24 кладки из 36
    # клеток: это уже головоломка «куда вообще можно пройти», а не платформер
    blocks_field = sum(1 for r in range(_ROWS) for c in range(_COLS)
                       if level.plat[r][c] == LO_BLOCK)
    maze = min(1.0, blocks_field / MAZE_FULL)

    # 10. одноразовое поле: доля клеток, которые исчезают после действия
    oneshot = sum(1 for r in range(_ROWS) for c in range(_COLS)
                  if level.plat[r][c] == LO_SHRINK_WORN2)
    oneshot_field = min(1.0, oneshot / (ONESHOT_FIELD_FULL / 6.0))

    parts = {
        "precision": precision,
        "irreversible": irreversible,
        "no_rest": no_rest,
        "forced_motion": forced,
        "hazard_goal": hazard_goal,
        "puzzle": puzzle,
        "trap_risk": trap_risk,
        "variety": variety,
        "maze": maze,
        "oneshot_field": oneshot_field,
    }
    interest = 100.0 * sum(WEIGHTS[k] * v for k, v in parts.items())

    out = dict(parts)
    out.update({
        "interest": round(interest, 1),
        "kinds": kinds,
        "support_cells": len(cells),
        "blocks_field": blocks_field,
        "oneshot_cells": oneshot,
        "longest_unstable_run": run,
        "slope_traps": len(traps),
        "fruits": goals["fruits"],
        "fruits_risky": goals["risky"],
        "fruits_on_hazard": goals["on_hazard"],
        "fruits_above_hazard": goals["above_hazard"],
        "must_collect_all": goals["must_collect_all"],
    })
    return out


def describe(score: dict) -> str:
    """Короткая строка для логов: из чего складывается интересность."""
    return (
        f"interest={score['interest']:.1f} "
        f"(точность={score['precision']:.0%}, "
        f"необратимость={score['irreversible']:.0%}, "
        f"без-отдыха={score['no_rest']:.0%}, "
        f"вынужденно={score['forced_motion']:.0%}, "
        f"риск-у-цели={score['hazard_goal']:.0%}, "
        f"головоломка={score['puzzle']:.0%}, "
        f"ловушки={score['trap_risk']:.0%}, "
        f"разнообразие={score['variety']:.0%})"
    )
