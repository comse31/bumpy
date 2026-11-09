#!/usr/bin/env python3
"""Генератор проходимых уровней Bumpy.

Уровень — это та же структура, что лежит в main/levels.json (сетка 6x6 слоя lo,
слой hi с вертикальными перегородками, сетка объектов, стартовая ячейка,
финальная ячейка и счётчик выхода), поэтому сгенерированный уровень можно без
изменений отдать в main/level/level.script.

Алгоритм:

  1. Из seed через random.Random строится «сырой» уровень: базовые платформы,
     препятствия (шипы, горящие/липкие/наклонные/сжимающиеся платформы, кладка),
     перегородки, объекты-расходники и коллектиблы (код >= 5), старт и выход.
  2. Кандидат упаковывается в dict формата levels.json и проверяется решателем
     tools/solve_level.py через is_solvable(): допустимыми считаются только
     уровни со статусом "solvable" (проходимые). "impossible" — брак,
     "limit" — неопределённость: такой кандидат отбрасывается, потому что
     сохранять в БД уровень, проходимость которого не доказана, нельзя.
  3. При отказе seed сдвигается (seed + 1) и делается следующая попытка, пока
     не будет найден проходимый уровень или не исчерпан лимит попыток.

Так как уровень полностью определяется seed, генерация воспроизводима: один и
тот же seed всегда даёт один и тот же уровень.

Использование:
    python3 tools/gen_level.py --seed 1                 # напечатать уровень (JSON)
    python3 tools/gen_level.py --seed 1 --out levels.json
    python3 tools/gen_level.py --seed 1 --requirements  # + требования по снаряжению
    python3 tools/gen_level.py --bench 50               # доля проходимых кандидатов
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import level_interest as li  # noqa: E402
import solve_level as sv  # noqa: E402

COLS = 6
ROWS = 6
CELLS = COLS * ROWS

# Коды слоя lo (см. main/level/level.script: PLATFORM_BY_CODE).
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

# Платформы, на которых НЕЛЬЗЯ начинать уровень: шар погибает в первом же
# касании (шипы) или без капли в кармане (горящая и горящая липкая). Старт на
# обычной, липкой и любой сжимающейся платформе (2/3/4) разрешён.
LETHAL_START_CODES = frozenset({LO_BURNING, LO_BURNING_STICKY, LO_SPIKE})

# Коды объектов (см. main/level/level.script: goodie_factory).
OBJ_HAMMER = 1
OBJ_KEY = 2
OBJ_DROP = 3
OBJ_HEART = 4
# Коллектиблы: коды >= 5, распределяются по фруктам по кругу.
OBJ_COLLECTIBLE_FIRST = 5
OBJ_COLLECTIBLE_LAST = 16  # 12 фруктов, дальше коды повторяются по кругу

# Коды слоя hi (перегородки): 1..3 — разрушаемые с разной прочностью, 4 — нет.
HI_WALL_WEAK = 1
HI_WALL_MEDIUM = 2
HI_WALL_STRONG = 3
HI_WALL_SOLID = 4

# Ячейка строки метаданных: row 0 — верх (как в levels.json).
def meta_rc(r: int, c: int) -> int:
    return r * COLS + c


def row_screen(r: int) -> int:
    """Строка метаданных (0 — верх) -> экранная (0 — низ)."""
    return (ROWS - 1) - r


class LevelGenerator:
    """Генерация одного кандидата уровня по seed (без проверки проходимости)."""

    def __init__(self, rng: random.Random, index: int = 1) -> None:
        self.rng = rng
        self.index = index

    # -- параметры сложности -------------------------------------------------

    def _counts(self) -> dict[str, int]:
        """Сколько чего ставить. Растёт с индексом уровня, но остаётся умеренным."""
        rng = self.rng
        step = min(10, max(0, self.index - 1) // 10)
        return {
            "extra_platforms": rng.randint(4, 8) + step,
            "spikes": rng.randint(0, 2) + step // 2,
            "burning": rng.randint(0, 2) + step // 3,
            "sticky": rng.randint(0, 2),
            "sloped": rng.randint(0, 2) + step // 4,
            "shrink": rng.randint(1, 3),
            "blocks": rng.randint(0, 1) + step // 5,
            "walls": rng.randint(0, 3) + step // 2,
            "hammers": rng.randint(0, 2),
            "keys": rng.randint(0, 2),
            "drops": rng.randint(0, 2),
            "hearts": rng.randint(0, 1),
            "collectibles": rng.randint(2, 5),
        }

    # -- вспомогательные операции над сетками --------------------------------

    def _empty_grids(self):
        lo = [[LO_EMPTY] * COLS for _ in range(ROWS)]
        hi = [[LO_EMPTY] * COLS for _ in range(ROWS)]
        obj = [[LO_EMPTY] * COLS for _ in range(ROWS)]
        return lo, hi, obj

    @staticmethod
    def _has_floor(lo, r: int, c: int) -> bool:
        """Есть ли в клетке (экранные координаты r, c) поверхность."""
        return lo[row_screen(r)][c] != LO_EMPTY

    def _build_floors(self, lo) -> None:
        """Базовый каркас: пол в нижнем ряду и несколько «этажей» платформ.

        Нижний ряд делаем сплошным (кроме стартовой и финальной колонок, где
        платформа не обязательна), а выше ставим короткие островки: так шар
        может перемещаться по уровню, но не застревает.
        """
        rng = self.rng
        # нижний ряд (экранный 0 = самая нижняя линия) — почти сплошной
        bottom = ROWS - 1
        for c in range(COLS):
            if rng.random() < 0.9:
                lo[bottom][c] = LO_DEFAULT
        # верхняя граница поля: пара платформ, чтобы было куда прыгать
        for c in range(COLS):
            if rng.random() < 0.35:
                lo[0][c] = LO_DEFAULT

        # островки на промежуточных рядах
        extra = self._counts()["extra_platforms"]
        for _ in range(extra):
            r = rng.randint(1, ROWS - 2)
            c = rng.randint(0, COLS - 1)
            lo[r][c] = LO_DEFAULT

        # «лестница»: связка по диагонали, чтобы у шара был подъём
        r0 = rng.randint(2, ROWS - 2)
        c0 = rng.randint(0, 1)
        for i in range(rng.randint(2, 4)):
            r = min(ROWS - 1, r0 + i)
            c = min(COLS - 1, c0 + i)
            if lo[r][c] == LO_EMPTY:
                lo[r][c] = LO_DEFAULT

    def _place_specials(self, lo, counts: dict[str, int]) -> None:
        """Расставить особые платформы на уже существующие клетки пола."""
        rng = self.rng
        cells = [(r, c) for r in range(ROWS) for c in range(COLS) if lo[r][c]]
        rng.shuffle(cells)
        pool = list(cells)

        def take() -> tuple[int, int] | None:
            return pool.pop() if pool else None

        for _ in range(counts["spikes"]):
            cell = take()
            if cell:
                lo[cell[0]][cell[1]] = LO_SPIKE
        for _ in range(counts["burning"]):
            cell = take()
            if cell:
                lo[cell[0]][cell[1]] = rng.choice([LO_BURNING, LO_BURNING_STICKY])
        for _ in range(counts["sticky"]):
            cell = take()
            if cell:
                lo[cell[0]][cell[1]] = LO_STICKY
        for _ in range(counts["sloped"]):
            cell = take()
            if cell:
                lo[cell[0]][cell[1]] = rng.choice([LO_SLOPE_LEFT, LO_SLOPE_RIGHT])
        for _ in range(counts["shrink"]):
            cell = take()
            if cell:
                lo[cell[0]][cell[1]] = rng.choice(
                    [LO_SHRINK, LO_SHRINK_WORN, LO_SHRINK_WORN2])
        for _ in range(counts["blocks"]):
            cell = take()
            if not cell:
                continue
            br, bc = cell
            # Кладку нельзя ставить ПОД платформой: «сразу над кладкой» не
            # должно быть платформ (правило оригинала — см.
            # blocks_above_violations). Иначе шар, разбивающий кладку снизу,
            # упирался бы в платформу.
            #
            # Разрешён только столбик кладки, поэтому смотрим ВВЕРХ по колонке
            # до первой непустой клетки: она обязана быть кладкой (или пусто
            # до верха). Проверять только соседнюю строку мало — платформа
            # может стоять через ряд, и после превращения промежуточных клеток
            # в кладку нарушение всё равно возникло бы.
            ok = True
            for rr in range(br - 1, -1, -1):
                code = lo[rr][bc]
                if code == LO_EMPTY:
                    continue
                ok = code == LO_BLOCK
                break
            if not ok:
                continue
            lo[br][bc] = LO_BLOCK

    def _place_walls(self, hi, counts: dict[str, int]) -> None:
        """Вертикальные перегородки. Последний столбец в данных всегда пуст."""
        rng = self.rng
        spots = [(r, gc) for r in range(ROWS) for gc in range(COLS - 1)]
        rng.shuffle(spots)
        used = 0
        for r, gc in spots:
            if used >= counts["walls"]:
                break
            # не ставим перегородку в каждой второй клетке подряд — уровень
            # становится «решёткой», из которой шар не выберется
            if hi[r][gc] != LO_EMPTY:
                continue
            hi[r][gc] = rng.choice(
                [HI_WALL_WEAK, HI_WALL_MEDIUM, HI_WALL_STRONG, HI_WALL_SOLID])
            used += 1

    def _place_objects(self, lo, obj, counts: dict[str, int],
                       start: tuple[int, int], exit_cell: tuple[int, int],
                       forbidden: set[tuple[int, int]] | None = None) -> int:
        """Расставить предметы. Возвращает число коллектиблов (timer).

        `forbidden` — клетки, куда предметы ставить НЕЛЬЗЯ (камера старта):
        подобранный в ней расходник обнулил бы требование уровня.
        """
        rng = self.rng
        busy = {start, exit_cell} | (forbidden or set())

        # свободные клетки: пустые или с платформой, но без опасных/особых
        candidates = []
        for r in range(ROWS):
            for c in range(COLS):
                if (r, c) in busy or obj[r][c] != LO_EMPTY:
                    continue
                if lo[r][c] in (LO_SPIKE, LO_BLOCK):
                    continue
                candidates.append((r, c))
        rng.shuffle(candidates)
        it = iter(candidates)

        def put(code: int, *, consumable: bool = False) -> bool:
            for cell in it:
                if obj[cell[0]][cell[1]] != LO_EMPTY:
                    continue
                # расходники (капля/ключ/молоток) в камере старта запрещены:
                # иначе шар подберёт их пролётом до замка
                if consumable and (r_ := cell[0], cell[1]) in (forbidden or set()):
                    continue
                obj[cell[0]][cell[1]] = code
                return True
            return False

        for code, key in ((OBJ_HAMMER, "hammers"), (OBJ_KEY, "keys"),
                          (OBJ_DROP, "drops"), (OBJ_HEART, "hearts")):
            for _ in range(counts[key]):
                put(code, consumable=True)

        collectibles = 0
        for i in range(counts["collectibles"]):
            code = OBJ_COLLECTIBLE_FIRST + (i % (OBJ_COLLECTIBLE_LAST - OBJ_COLLECTIBLE_FIRST + 1))
            if put(code):
                collectibles += 1
        return collectibles

    def _pick_start(self, lo) -> tuple[int, int]:
        """Старт: безопасная платформа в нижней половине уровня.

        Смертельные поверхности (горящая 8, горящая липкая 9, шипы 12) не
        выбираются: игра не должна начинаться с потери жизни или смерти без
        капли. Сжимающаяся платформа любого остатка (2/3/4) допустима — игрок
        сам решает, как её использовать.
        """
        rng = self.rng
        options = [(r, c) for r in range(ROWS // 2, ROWS) for c in range(COLS)
                   if lo[r][c] != LO_EMPTY
                   and lo[r][c] != LO_BLOCK
                   and lo[r][c] not in LETHAL_START_CODES]
        if not options:
            # запасной вариант: (ROWS-1, 0), безопасный код выставит generate()
            return (ROWS - 1, 0)
        return rng.choice(options)

    def _lock_start(self, lo, hi, start: tuple[int, int]) -> set[tuple[int, int]]:
        """Запереть шар на старте так, чтобы выход требовал предмет.

        Замок состоит из двух частей:

          * "block" — кладка прямо над стартом: ломается ТОЛЬКО молотком
            (ставится, если над стартом есть ряд);
          * "wall"  — разрушаемая перегородка в ряду старта: ломается ключом,
            плюс неразрушаемые перегородки выше по бокам колонки.

        Замка «горящая платформа под шаром» больше нет: игра не должна
        начинаться со смерти в огне (см. LETHAL_START_CODES), поэтому капля
        на старте не востребована и стартовая платформа остаётся безопасной.

        Возвращает множество клеток «камеры»: в них нельзя ставить предметы,
        иначе шар подберёт нужный расходник, не выходя из камеры, и уровень
        перестанет требовать снаряжение.
        """
        rng = self.rng
        sr, sc = start
        forbidden: set[tuple[int, int]] = set()

        # ВАЖНО: `lo` — сетка в МЕТА-координатах (строка 0 — ВЕРХ экрана, как в
        # levels.json), а для шара «вверх» — это meta_row - 1 (решатель делает
        # screen_row = ROWS - 1 - meta_row). Поэтому «потолок» камеры — строка
        # sr - 1, а не sr + 1.
        sr_above = sr - 1
        has_ceiling = sr_above >= 0
        # Стены по бокам ставятся ВСЕГДА, иначе шар просто хопнет в соседнюю
        # колонку и выйдет из камеры без затрат.
        #
        # Замок строится ТОЛЬКО сверху (кладка — молоток) и по бокам
        # (разрушаемая перегородка в ряду старта — ключ). Горящую платформу
        # под шаром ставить нельзя: игра не должна начинаться со смерти в огне
        # (см. LETHAL_START_CODES). Вариант "wall" — это прежний "burning" без
        # огня под шаром.
        kind = rng.choice(("block", "wall")) if has_ceiling else "wall"

        # Тип стартовой платформы сохраняется, если она безопасна: обычная,
        # липкая и любая сжимающаяся подходят. Смертельные и служебные
        # (пусто/кладка) заменяются обычной платформой.
        if lo[sr][sc] in LETHAL_START_CODES or lo[sr][sc] in (LO_EMPTY, LO_BLOCK):
            lo[sr][sc] = LO_DEFAULT

        # Перегородки по бокам колонки старта на ВСЕХ рядах от старта до верха:
        # в ряду старта стена блокирует только хоп, а при высоком прыжке шар
        # поднимается и отводится в сторону на другом ряду.
        #
        # В ряду СТАРТА стена разрушаемая (это и есть «дверь», за которую
        # платят ключом), а ВЫШЕ — неразрушаемая. Иначе шар мог бы ломать
        # любую стену колонки, и у решателя появлялось много равнозначных
        # ветвей: перебор разрастался с 0.05 с до 30+ с на кандидата.
        # С неразрушаемыми стенами выше выход из камеры единственный.
        # (hi[r][gc] — граница между колонками gc и gc+1; последний
        # столбец gc = COLS-1 в данных не используется)
        for r in range(0, sr + 1):
            code = HI_WALL_WEAK if r == sr else HI_WALL_SOLID
            if sc > 0:
                hi[r][sc - 1] = code
            if sc < COLS - 1:
                hi[r][sc] = code

        if kind == "block":
            # Кладка над шаром: ломается только снизу молотком, и заодно
            # закрывает выход вверх через высокий прыжок.
            #
            # Правило геометрии: НАД кладкой не может быть платформ
            # (см. blocks_above_violations; в оригинале над кладкой стоит
            # только другая кладка — столбик кирпичей). Поэтому платформы выше
            # по этой колонке убираются: иначе шар, разбивающий кладку снизу,
            # упирался бы в платформу сверху.
            lo[sr_above][sc] = LO_BLOCK
            forbidden.add((sr_above, sc))
            for rr in range(sr_above - 1, -1, -1):
                if lo[rr][sc] in PLATFORM_CODES:
                    # платформа над кладкой недопустима — просто убираем её
                    lo[rr][sc] = LO_EMPTY
                    forbidden.add((rr, sc))
                elif lo[rr][sc] == LO_BLOCK:
                    # столбик кладки допустим, но выше него платформ быть не
                    # должно — продолжаем проверку
                    continue
                else:
                    # пусто или что-то ещё — выше препятствий для правила нет
                    break

        # «Камера» — полоса ряда старта ПЛЮС вся колонка старта выше него:
        # шар поднимается высоким прыжком именно по своей колонке и подбирает
        # предметы пролётом, поэтому расходник в любом ряду этой колонки
        # обнулил бы требование уровня (проверено на seed 8002: ключ в (2,0)
        # подбирался до того, как шар ломал стену).
        for c in range(COLS):
            forbidden.add((sr, c))
        for r in range(ROWS):
            forbidden.add((r, sc))
        return forbidden

    def _pick_exit(self, lo, start: tuple[int, int]) -> tuple[int, int]:
        """Выход: клетка с платформой, максимально далеко от старта."""
        options = [(r, c) for r in range(ROWS) for c in range(COLS)
                   if (r, c) != start
                   and lo[r][c] not in (LO_EMPTY, LO_SPIKE, LO_BLOCK)]
        if not options:
            return (0, COLS - 1)

        def dist(cell):
            return abs(cell[0] - start[0]) * COLS + abs(cell[1] - start[1])

        return max(options, key=dist)

    # -- сборка --------------------------------------------------------------

    def generate(self) -> dict:
        lo, hi, obj = self._empty_grids()
        counts = self._counts()
        self._build_floors(lo)
        self._place_specials(lo, counts)
        self._place_walls(hi, counts)

        start = self._pick_start(lo)
        # Замок на старте: уровень обязан требовать хотя бы один предмет.
        # Если сверху нет ряда (старт в верхнем ряду), берём старт на ряд ниже.
        if start[0] + 1 >= ROWS:
            start = (ROWS - 2, start[1])
            lo[start[0]][start[1]] = LO_DEFAULT
        # Стартовая клетка обязана быть безопасной поверхностью: шар не должен
        # появляться в огне или на шипах даже при запасном варианте старта.
        if lo[start[0]][start[1]] in LETHAL_START_CODES \
                or lo[start[0]][start[1]] in (LO_EMPTY, LO_BLOCK):
            lo[start[0]][start[1]] = LO_DEFAULT
        forbidden = self._lock_start(lo, hi, start)

        exit_cell = self._pick_exit(lo, start)
        timer = self._place_objects(lo, obj, counts, start, exit_cell,
                                    forbidden=forbidden)

        # платформа в клетке выхода будет удалена при открытии выхода, но для
        # решателя она должна существовать: выход всегда на клетке с полом
        if lo[exit_cell[0]][exit_cell[1]] == LO_EMPTY:
            lo[exit_cell[0]][exit_cell[1]] = LO_DEFAULT

        return {
            "level": self.index,
            "grid_lo": lo,
            "grid_hi": hi,
            "objects": obj,
            "raw_grid": [v for row in lo for v in row],
            "start_cell": meta_rc(*start),
            "timer": timer,
            "timer_cell": meta_rc(*exit_cell),
            "theme": self.rng.randint(1, 7),
            # служебные поля сгенерированного уровня (в levels.json их нет,
            # level.script их игнорирует)
            "seed": self.rng.randrange(1 << 31),
            "generated": True,
        }


# Код кирпичной кладки в слое lo (main/level/level.script: PLATFORM_BY_CODE).
PLATFORM_CODES = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9})


def lethal_start_violation(level: dict) -> int | None:
    """Код платформы в стартовой клетке, если начинать на ней смертельно.

    Возвращает код lo-слоя (8 — горящая, 9 — горящая липкая, 12 — шипы) или
    None. Правило: главный герой не может на старте сразу погибнуть, поэтому
    старт на огне и шипах запрещён. Сжимающаяся платформа любого остатка
    разрешена — это осознанное решение игрока, а не мгновенная смерть.
    """
    cell = int(level["start_cell"])
    row, col = divmod(cell, COLS)
    code = int(level["grid_lo"][row][col])
    return code if code in LETHAL_START_CODES else None


def blocks_above_violations(level: dict) -> list[tuple[int, int, int]]:
    """Клетки, где НАД кладкой стоит платформа: [(row, col, код_выше)].

    В оригинальных уровнях (main/levels.json, 144 кладки) прямо над кладкой
    стоит только другая кладка — столбик кирпичей. Платформы над кладкой нет
    ни в одном уровне: шар, разбивающий кладку снизу, упирался бы в платформу,
    а геометрия проёма переставала бы быть «пробиваемой» снизу.

    Поэтому генератор такие сочетания запрещает, а проверка продублирована
    отдельной функцией — её используют и тесты, и `is_playable()`.
    """
    lo = level["grid_lo"]
    bad = []
    for row in range(ROWS):
        for col in range(COLS):
            if lo[row][col] != LO_BLOCK or row == 0:
                continue
            above = lo[row - 1][col]
            if above in PLATFORM_CODES:
                bad.append((row, col, above))
    return bad


def candidate(seed: int, index: int = 1) -> dict:
    """Один кандидат уровня по seed (без проверки проходимости)."""
    rng = random.Random(seed)
    level = LevelGenerator(rng, index).generate()
    level["seed"] = seed
    return level


# Минимальное число предметов, которое уровень обязан требовать на старте.
# Требование «хотя бы один любой предмет» делает уровни интереснее: шар не
# может пройти уровень «с нуля», игроку нужен хотя бы один молоток, ключ или
# капля, добытые на самом уровне или взятые в карман.
MIN_REQUIRED_ITEMS = 1


def solve_candidate(level: dict, node_cap: int = 400000) -> dict:
    """Один вызов решателя на кандидата (без повторного solve).

    Возвращает результат solve() целиком: статус, требуемые предметы и план
    действий. План нужен для оценки «человеческой» интересности, поэтому
    отдельный вызов решателя ради этой оценки делать нельзя — это удвоило бы
    время генерации.
    """
    return sv.solve(sv.Level(level), node_cap=node_cap, legacy=True,
                    allow_fallback=True)


def evaluate(level: dict, node_cap: int = 400000) -> tuple[str, tuple[int, int, int]]:
    """Один вызов решателя: (статус, минимальный стартовый набор предметов).

    `is_solvable()` отдельно от `solve()` вызывать не нужно: solve() уже
    возвращает и статус, и required. Раньше генератор делал ДВА прохода
    решателя на кандидата (is_solvable + solve), из-за чего проверка одного
    уровня занимала десятки секунд; теперь — один проход.
    """
    res = solve_candidate(level, node_cap=node_cap)
    status = res.get("status", "impossible")
    required = tuple(int(v) for v in res.get("required", (0, 0, 0)))
    return status, required


# Минимальная «человеческая» интересность, которую генератор считает
# приемлемой. Ниже — уровни, где всё держится на однообразных хопах:
# они проходимы, но играть в них скучно. Порог откалиброван по замеру
# `--bench` на 25 seed'ах: у принятых генератором кандидатов интересность
# 20..32 (средняя ~26), у классических уровней — до 50. Порог ниже среднего
# сознательно: иначе генератор отбрасывал бы больше половины проходимых
# уровней и заметно замедлялся, а «подтягивает» качество именно отбор
# лучшего из пула (DEFAULT_INTEREST_POOL).
MIN_INTEREST = 26.0
# Сколько подходящих кандидатов оценить, прежде чем выбрать лучший.
# Поиск интересного уровня идёт «пачкой»: первый приемлемый может оказаться
# слишком пресным, поэтому генератор смотрит на несколько и берёт максимум.
DEFAULT_INTEREST_POOL = 4


def interest_of(level: dict, res: dict | None = None,
                node_cap: int = 400000) -> dict:
    """Оценка «человеческой» интересности уровня (tools/level_interest.py).

    `res` — уже полученный результат решателя; если его нет, считается заново
    (нужен план действий). Оценка не влияет на проходимость: она только
    помогает выбрать из нескольких проходимых кандидатов менее скучный.
    """
    if res is None:
        res = solve_candidate(level, node_cap=node_cap)
    if res.get("status") != "solvable" or not res.get("actions"):
        return {"interest": 0.0}
    return li.analyze(sv.Level(level), res)


def evaluate_candidate(level: dict, node_cap: int = 400000,
                       min_items: int = 0, min_interest: float = 0.0
                       ) -> tuple[str, dict | None, dict | None]:
    """Статус + результат решателя + оценка интересности за ОДИН проход.

    Возвращает (status, res, score):
      * status — "solvable" / "impossible" / "limit";
      * res    — результат solve() (он же нужен для требований и интересности);
      * score  — оценка level_interest.analyze (только для "solvable").

    Один проход важен по времени: `solve()` — самая дорогая операция генератора,
    и раньше проверка + оценка делали её дважды на одного кандидата.
    """
    if blocks_above_violations(level):
        return "impossible", None, None
    if lethal_start_violation(level) is not None:
        return "impossible", None, None

    res = solve_candidate(level, node_cap=node_cap)
    status = res.get("status", "impossible")
    if status != "solvable":
        return status, res, None
    required = tuple(int(v) for v in res.get("required", (0, 0, 0)))
    if min_items > 0 and sum(required) < min_items:
        # проходим, но слишком просто: для генератора это брак
        return "impossible", res, None
    score = interest_of(level, res, node_cap=node_cap)
    if min_interest > 0 and score.get("interest", 0.0) < min_interest:
        # проходим, но скучен: генератор возьмёт следующий seed
        return "impossible", res, score
    return status, res, score


def is_playable(level: dict, node_cap: int = 400000,
                min_items: int = 0, min_interest: float = 0.0) -> str:
    """Статус решателя для кандидата: "solvable" / "impossible" / "limit".

    При `min_items > 0` уровень считается неподходящим, если суммарное
    требование на старте (drops + keys + hammers) меньше `min_items`:
    возвращается "impossible", чтобы вызывающий код взял следующий seed.

    При `min_interest > 0` дополнительно отбрасываются проходимые, но скучные
    уровни: «человеческая» интересность ниже порога — брак, чтобы генератор
    искал следующий seed.
    """
    status, _res, _score = evaluate_candidate(
        level, node_cap=node_cap, min_items=min_items,
        min_interest=min_interest)
    return status


def generate_playable(seed: int, index: int = 1, *, attempts: int = 400,
                      node_cap: int = 400000,
                      min_items: int = MIN_REQUIRED_ITEMS,
                      min_interest: float = MIN_INTEREST,
                      interest_pool: int = DEFAULT_INTEREST_POOL,
                      on_attempt=None) -> dict | None:
    """Лучший по интересности подходящий уровень, начиная с seed.

    seed перебирается последовательно (seed, seed+1, ...): результат
    воспроизводим и не зависит от состояния ГСЧ между вызовами. Принимается
    только "solvable"; "impossible" (в т.ч. уровни без обязательных предметов
    при min_items > 0 и скучные при min_interest > 0) — брак, "limit" —
    недоказанная проходимость (такой уровень нельзя сохранять в БД).

    Из подходящих кандидатов берётся не первый, а самый интересный: первые
    `interest_pool` прошедших проверку уровней оцениваются
    (tools/level_interest.py), и в результат идёт лучший. Это делает
    генерируемые уровни разнообразнее: без отбора игра часто получала просто
    «ещё один набор хопов» с формально выполненными правилами.
    """
    best = None
    best_score = -1.0
    pool_left = max(1, interest_pool)
    for offset in range(max(1, attempts)):
        cur = seed + offset
        level = candidate(cur, index)
        if len(level["raw_grid"]) != CELLS:
            continue
        status, _res, score = evaluate_candidate(
            level, node_cap=node_cap, min_items=min_items,
            min_interest=min_interest)
        if on_attempt:
            on_attempt(cur, status)
        if status != "solvable" or not score:
            continue
        value = float(score.get("interest", 0.0))
        if value > best_score:
            best_score = value
            best = level
            best["interest"] = value
            best["interest_parts"] = {
                key: round(v, 3) for key, v in score.items()
                if key not in ("interest", "kinds")
            }
        pool_left -= 1
        if pool_left <= 0:
            break
    if best is not None and on_attempt:
        on_attempt(best.get("seed"), f"selected interest={best_score:.1f}")
    return best


def requirements(level: dict, node_cap: int = 400000) -> dict:
    """Минимальный стартовый набор предметов для уровня (как gen_level_requirements)."""
    res = sv.solve(sv.Level(level), node_cap=node_cap)
    req = res.get("required", (0, 0, 0))
    return {
        "drops": int(req[0]),
        "keys": int(req[1]),
        "hammers": int(req[2]),
        "status": res.get("status"),
        "optimal": bool(res.get("optimal", False)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Генератор проходимых уровней Bumpy.")
    ap.add_argument("--seed", type=int, default=None,
                    help="стартовый seed (по умолчанию — текущее время)")
    ap.add_argument("--level", type=int, default=1,
                    help="номер уровня для поля level (влияет на сложность)")
    ap.add_argument("--attempts", type=int, default=400,
                    help="сколько seed'ов перебрать до отказа")
    ap.add_argument("--node-cap", type=int, default=400000,
                    help="лимит узлов решателя на кандидата")
    ap.add_argument("--out", default=None, help="записать уровень в файл")
    ap.add_argument("--requirements", action="store_true",
                    help="добавить минимальный набор предметов (solve, медленно)")
    ap.add_argument("--min-items", type=int, default=MIN_REQUIRED_ITEMS,
                    help=("сколько предметов уровень обязан требовать на старте "
                          f"(по умолчанию {MIN_REQUIRED_ITEMS}; 0 — не требовать)"))
    ap.add_argument("--min-interest", type=float, default=MIN_INTEREST,
                    help=("минимальная «человеческая» интересность 0..100 "
                          f"(по умолчанию {MIN_INTEREST}; 0 — не проверять)"))
    ap.add_argument("--interest-pool", type=int, default=DEFAULT_INTEREST_POOL,
                    help=("из скольких подходящих кандидатов выбрать самый "
                          f"интересный (по умолчанию {DEFAULT_INTEREST_POOL})"))
    ap.add_argument("--bench", type=int, default=0,
                    help="оценить долю подходящих кандидатов на N seed'ах")
    args = ap.parse_args()

    if args.bench:
        import time
        stats = {"solvable": 0, "impossible": 0, "limit": 0}
        interests = []
        start = time.time()
        n = max(1, args.bench)
        for i in range(n):
            level = candidate(1000 + i, args.level)
            # считаем те же условия, что и у генератора: solvable + минимум
            # предметов + порог интересности
            status = is_playable(level, args.node_cap, min_items=args.min_items,
                                 min_interest=args.min_interest)
            stats[status] = stats.get(status, 0) + 1
            if status == "solvable":
                score = interest_of(level, node_cap=args.node_cap)
                interests.append(score.get("interest", 0.0))
                print(f"  seed {1000 + i}: {status} "
                      f"interest={score.get('interest', 0.0):.1f}")
            else:
                print(f"  seed {1000 + i}: {status}")
        elapsed = time.time() - start
        print()
        print(f"кандидатов: {n}, за {elapsed:.1f} с "
              f"({elapsed / n:.2f} с/шт)")
        for key, value in stats.items():
            print(f"  {key}: {value} ({100 * value / n:.0f}%)")
        if interests:
            print(f"  интересность: средняя {sum(interests) / len(interests):.1f}, "
                  f"мин {min(interests):.1f}, макс {max(interests):.1f}")
        return

    seed = args.seed if args.seed is not None else int(__import__("time").time())
    level = generate_playable(seed, args.level, attempts=args.attempts,
                              node_cap=args.node_cap,
                              min_items=args.min_items,
                              min_interest=args.min_interest,
                              interest_pool=args.interest_pool,
                              on_attempt=lambda s, st: print(f"  seed {s}: {st}"))
    if level is None:
        print(f"не удалось найти подходящий уровень на {args.attempts} попытках",
              file=sys.stderr)
        raise SystemExit(1)

    if args.requirements:
        level["requirements"] = requirements(level, args.node_cap)

    text = json.dumps(level, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")
        print(f"записано: {args.out} (seed {level['seed']})")
    else:
        print(text)


if __name__ == "__main__":
    main()
