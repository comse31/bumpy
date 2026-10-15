#!/usr/bin/env python3
"""Офлайн-анализатор и решатель уровней Bumpy.

Скрипт читает метаданные уровней (main/levels.json), строит для каждого уровня
граф перемещений шара, ищет план прохождения (последовательность действий шара),
считает сложность по трём критериям из задания и сортирует уровни.

Модель движения повторяет правила main/ball/ball.script:
  * шар покоится на «опорной» ячейке (платформа или верх кирпичной кладки);
  * обычный прыжок влево/вправо (hop) смещает шар на соседнюю колонку того же
    ряда; если там нет опоры — шар пролетает колонку вниз до ближайшей опоры
    (или гибнет, упав за нижний край);
  * высокий прыжок (high jump) поднимает шар вверх по колонке; в момент
    пересечения уровня каждого ряда игрок может нажать влево/вправо, и шар
    смещается на соседнюю колонку в этом ряду, после чего падает до опоры —
    это единственный способ подниматься (прямо вверх мешает платформа/кладка
    сверху в той же колонке);
  * липкая платформа — шар лежит на ней и может только скатиться (roll) в
    соседнюю колонку, высокий прыжок недоступен;
  * наклонная платформа — шар неуправляемо отскакивает в сторону наклона;
  * шипы — смерть; горящая платформа — смерть без капли (капля гасит);
  * разрушаемая перегородка открывается за ключи (по одному на удар);
  * кирпичная кладка разбивается снизу молотком (один молоток на стену).

Шар собирает предметы, пролетая через ячейку (как в игре — по фактической
позиции шара каждый кадр), поэтому в модели учитывается весь путь движения,
а не только точка приземления.

Сложность (по критериям задания):
  1. traps        — количество ловушек (шипы, горящие, сжимающиеся, липкие,
                    наклонные платформы);
  2. simultaneous — обязательные одновременные действия (высокие прыжки с
                    перестроением в полёте, скатывания с липких, вынужденные
                    отскоки с наклонных, ресурсные «замки»);
  3. no_rest      — невозможность задержаться на месте (ячейки плана, где шар
                    не может спокойно стоять: наклонные/липкие/сжимающиеся/
                    горящие).

Использование:
    python tools/level_solver.py                 # все уровни -> отчёт + JSON
    python tools/level_solver.py --level 1 --verbose
    python tools/level_solver.py --quiet         # без построчного прогресса
"""

import argparse
import json
import os
import sys
from collections import deque

ROWS = 6
COLS = 6
TOP = ROWS - 1

# --- коды слоя lo -----------------------------------------------------------
STANDABLE_CODES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 12}  # кладка (10) не «стоится» напрямую
STICKY_CODE = 5
STICKY_BURNING_CODE = 9
SLOPE_DIR = {6: -1, 7: 1}  # 6 — наклон влево, 7 — вправо
BURNING_CODES = {8, 9}
SPIKE_CODE = 12
SHRINK_CODES = {2, 3, 4}
BLOCK_CODE = 10

# --- коды слоя hi (перегородки) ---------------------------------------------
WALL_DURABILITY = {1: 1, 2: 2, 3: 3}  # оставшаяся прочность
WALL_INDESTRUCTIBLE = 4

# --- коды объектов ----------------------------------------------------------
OBJ_HAMMER = 1
OBJ_KEY = 2
OBJ_DROP = 3
OBJ_HEART = 4
COLLECTIBLE_MIN = 5  # коды >= 5 открывают выход

# --- веса критериев сложности (можно менять) --------------------------------
W_TRAPS = 1.0          # каждая ловушка на уровне
W_TRAPS_PATH = 1.5     # каждая ловушка на пути прохождения
W_SIMULTANEOUS = 3.0   # каждое обязательное одновременное действие
W_NO_REST = 2.0        # каждая ячейка, где нельзя задержаться
W_RESOURCES = 2.0      # каждый обязательный расход снаряжения
W_MOVES = 0.15         # длина плана (объём работы игрока)

DEFAULT_LEVELS = os.path.join(os.path.dirname(__file__), "..", "main", "levels.json")
DEFAULT_JSON_OUT = os.path.join(os.path.dirname(__file__), "levels_ranked.json")
DEFAULT_MD_OUT = os.path.join(os.path.dirname(__file__), "LEVELS_RANKED.md")


def cell_to_rc(cell):
    """Индекс ячейки метаданных (row*6+col, строка 0 — верх) -> (row, col), row 0 — низ."""
    return TOP - (cell // COLS), cell % COLS


def rc_to_cell(row, col):
    return (TOP - row) * COLS + col


class Level:
    """Уровень в экранных координатах: row 0 — нижний ряд, col 0 — левая колонка."""

    def __init__(self, data):
        self.index = data["level"]
        self.theme = data.get("theme", 1)
        self.timer = data["timer"]
        self.lo = [[data["grid_lo"][TOP - r][c] for c in range(COLS)] for r in range(ROWS)]
        self.obj = [[data["objects"][TOP - r][c] for c in range(COLS)] for r in range(ROWS)]
        # перегородки: json grid_hi[gr][gc] -> граница b = gc+1 в экранной строке
        self.wall = [[0] * (COLS + 1) for _ in range(ROWS)]
        for gr in range(ROWS):
            r = TOP - gr
            for gc in range(COLS - 1):
                self.wall[r][gc + 1] = data["grid_hi"][gr][gc]
        self.start = cell_to_rc(data["start_cell"])
        self.exit = cell_to_rc(data["timer_cell"])
        self.collectibles = [
            (r, c)
            for r in range(ROWS)
            for c in range(COLS)
            if self.obj[r][c] >= COLLECTIBLE_MIN
        ]
        self.collectible_index = {rc: i for i, rc in enumerate(self.collectibles)}

    # ---- свойства ячеек -----------------------------------------------------
    def standable(self, r, c):
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return False
        if self.lo[r][c] in STANDABLE_CODES:
            return True
        # верх кирпичной кладки: кладка в ячейке ниже занимает весь ряд
        return r >= 1 and self.lo[r - 1][c] == BLOCK_CODE

    def support_below(self, r, c):
        for rr in range(r - 1, -1, -1):
            if self.standable(rr, c):
                return rr
        return None

    def has_block(self, r, c):
        return 0 <= r < ROWS and 0 <= c < COLS and self.lo[r][c] == BLOCK_CODE

    def is_sticky(self, r, c):
        return self.lo[r][c] in (STICKY_CODE, STICKY_BURNING_CODE)

    def is_slope(self, r, c):
        return self.lo[r][c] in SLOPE_DIR

    def is_burning(self, r, c, world=frozenset()):
        """Горящая платформа (8/9), ещё не погашенная каплей."""
        return self.lo[r][c] in BURNING_CODES and ("burn", r, c) not in world

    def is_spike(self, r, c):
        return self.lo[r][c] == SPIKE_CODE

    def is_shrink(self, r, c):
        return self.lo[r][c] in SHRINK_CODES

    def rest_mode(self, r, c):
        """В каком режиме шар покоится в ячейке.

        * 'sticky' — липкая платформа: только скатывание, без высокого прыжка;
        * 'slope'  — наклонная: задержаться нельзя, отскок в сторону наклона;
        * 'locked' — верх кирпичной кладки: можно прыгать, но не высоко;
        * 'normal' — обычная платформа.
        """
        if self.is_slope(r, c):
            return "slope"
        if self.is_sticky(r, c):
            return "sticky"
        if r >= 1 and self.lo[r - 1][c] == BLOCK_CODE:
            return "locked"
        return "normal"

    def wall_code(self, r, c, d):
        """Код перегородки на границе между колонками c и c+d (0 — нет)."""
        nc = c + d
        if nc < 0 or nc >= COLS:
            return WALL_INDESTRUCTIBLE  # внешняя граница поля — стекло
        b = c + 1 if d > 0 else c
        return self.wall[r][b]

    # ---- перемещения --------------------------------------------------------
    # Результат перемещения: (status, land_cell, path)
    #   status: 'rest' | 'death' | 'wall' | 'blocked'
    #   land_cell: (row, col) опоры при 'rest', иначе None
    #   path: список пройденных ячеек (без стартовой), последняя — точка опоры
    def hop_landing(self, r, c, d, world, depth=0):
        if depth > 12:
            return ("rest", (r, c), [])
        nc = c + d
        if nc < 0 or nc >= COLS:
            return ("blocked", None, [])
        b = c + 1 if d > 0 else c
        code = self.wall[r][b]
        if ("wall", r, b) in world:
            code = 0
        if code == WALL_INDESTRUCTIBLE:
            return ("blocked", None, [])
        if code in WALL_DURABILITY:
            return ("wall", None, [])
        if self.has_block(r, nc) and ("block", r, nc) not in world:
            return ("blocked", None, [])
        # колонка nc: либо платформа в ряду r, либо падение до опоры ниже
        if self.standable(r, nc):
            lr = r
        else:
            lr = self.support_below(r, nc)
            if lr is None:
                # падение за нижний край: шар пролетает всю колонку и гибнет
                path = [(rr, nc) for rr in range(r, -1, -1)]
                return ("death", None, path)
        path = [(rr, nc) for rr in range(r, lr - 1, -1)]
        return self.resolve_slope(lr, nc, world, path, depth)

    def resolve_slope(self, r, c, world, path, depth=0):
        """Наклонная платформа: шар неуправляемо отскакивает в сторону наклона."""
        if depth > 12:
            return ("rest", (r, c), path)
        if self.is_slope(r, c):
            d = SLOPE_DIR[self.lo[r][c]]
            res = self.hop_landing(r, c, d, world, depth + 1)
            if res[0] == "rest":
                return ("rest", res[1], path + res[2])
            if res[0] == "death":
                return ("death", None, path + res[2])
            # препятствие: шар возвращается на наклонную платформу
            return ("rest", (r, c), path)
        return ("rest", (r, c), path)

    def shift_rows(self, r, c):
        """Ряды выше r, на которых шар может перестроиться во время высокого прыжка."""
        rows = []
        for rr in range(r + 1, ROWS):
            if self.lo[rr][c] != 0:  # платформа/кладка выше — подъём прекращается
                break
            rows.append(rr)
        return rows

    def high_jump_rise(self, r, c):
        """Высокий прыжок без перестроения: подъём по своей колонке и возврат.

        Позволяет собрать предметы в ячейках выше (шар пролетает через них), даже
        если перестроиться в сторону некуда. Возвращает путь (без стартовой ячейки)
        или None, если подниматься некуда.
        """
        rows = self.shift_rows(r, c)
        if not rows:
            return None
        top = rows[-1]
        return [(rr, c) for rr in range(r + 1, top + 1)]

    def high_jump_edges(self, r, c, world):
        """Высокий прыжок с перестроением: (shift_row, d, result)."""
        edges = []
        for sr in self.shift_rows(r, c):
            rise = [(rr, c) for rr in range(r + 1, sr + 1)]
            for d in (-1, 1):
                res = self.hop_landing(sr, c, d, world)
                if res[0] == "rest":
                    # путь: подъём по своей колонке + падение в целевой
                    edges.append((sr, d, ("rest", res[1], rise + res[2])))
                elif res[0] == "death":
                    edges.append((sr, d, ("death", None, rise + res[2])))
                # wall/blocked — перестроение не удалось (шар возвращается вниз)
        return edges

    def can_break_wall(self, r, c, d, world):
        nc = c + d
        if nc < 0 or nc >= COLS:
            return None
        b = c + 1 if d > 0 else c
        code = self.wall[r][b]
        if code in WALL_DURABILITY and ("wall", r, b) not in world:
            return (b, code)
        return None

    def can_break_block(self, r, c, world):
        """Можно ли разбить кладку снизу из текущей колонки (нужен молоток)."""
        for rr in range(r + 1, ROWS):
            if self.lo[rr][c] == BLOCK_CODE and ("block", rr, c) not in world:
                return (rr, c)
            if self.lo[rr][c] != 0:
                return None
        return None


def solve(level, verbose=False, max_states=300000, res=(0, 0, 0)):
    """Поиск плана прохождения: собрать все collectibles и дойти до выхода.

    Состояние: (cell, mask, world, keys, hammers, drops). res — стартовое
    снаряжение в кармане (переносится с предыдущих уровней). Возвращает
    (plan, keys_end, hammers_end, drops_end) или None, если пройти нельзя.
    """
    all_collect = (1 << len(level.collectibles)) - 1
    start = level.start
    exit_rc = level.exit
    r0_keys, r0_hammers, r0_drops = res

    def collect(mask, cells):
        for cell in cells:
            i = level.collectible_index.get(cell)
            if i is not None:
                mask |= 1 << i
        return mask

    def pickup(world, cells, keys, hammers, drops):
        for cell in cells:
            if cell in world:
                continue
            r, c = cell
            code = level.obj[r][c]
            if code == OBJ_KEY:
                world = world | {("pick", r, c)}
                keys += 1
            elif code == OBJ_HAMMER:
                world = world | {("pick", r, c)}
                hammers += 1
            elif code == OBJ_DROP:
                world = world | {("pick", r, c)}
                drops += 1
        return world, keys, hammers, drops

    start_mask = collect(0, [start])
    init = (start, start_mask, frozenset(), r0_keys, r0_hammers, r0_drops)
    seen = {init: None}
    queue = deque([init])
    goal_state = None

    while queue:
        if len(seen) > max_states:
            return None
        state = queue.popleft()
        (cell, mask, world, keys, hammers, drops) = state
        r, c = cell
        if mask == all_collect and cell == exit_rc:
            goal_state = state
            break

        def push(nstate, action):
            if nstate not in seen:
                seen[nstate] = (state, action)
                queue.append(nstate)

        def arrive(path, action):
            """Обработка прибытия: собрать предметы по пути и проверить опасность
            в точке приземления (шар собирает предметы пролетая, а гибнет только
            при касании опасной платформы)."""
            nmask = mask
            nworld = world
            nkeys, nhammers, ndrops = keys, hammers, drops
            # предметы собираются по всей траектории (в игре — по позиции шара)
            nmask = collect(nmask, path)
            nworld, nkeys, nhammers, ndrops = pickup(nworld, path, nkeys, nhammers, ndrops)
            # опасность — только в точке приземления
            land = path[-1]
            lr, lc = land
            if level.is_spike(lr, lc):
                return
            if level.is_burning(lr, lc, nworld):
                if ndrops <= 0:
                    return
                ndrops -= 1
                nworld = nworld | {("burn", lr, lc)}
            push((land, nmask, nworld, nkeys, nhammers, ndrops), action)

        # --- обычные прыжки и скатывания ------------------------------------
        for d in (-1, 1):
            st, land, path = level.hop_landing(r, c, d, world)
            if st != "rest":
                continue
            arrive(path, ("hop", d, land[0], land[1]))

        # --- высокий прыжок с перестроением в полёте -------------------------
        if level.rest_mode(r, c) != "sticky":
            for sr, d, res in level.high_jump_edges(r, c, world):
                st, land, path = res
                if st != "rest":
                    continue
                arrive(path, ("highjump", sr, d, land[0], land[1]))
            # высокий прыжок без перестроения: подъём и возврат (сбор по пути)
            rise = level.high_jump_rise(r, c)
            if rise:
                arrive(rise, ("highjump_up", tuple(rise)))

        # --- разбить перегородку (ключи) ------------------------------------
        for d in (-1, 1):
            info = level.can_break_wall(r, c, d, world)
            if not info:
                continue
            b, code = info
            need = WALL_DURABILITY[code]
            if keys >= need:
                push((cell, mask, world | {("wall", r, b)}, keys - need, hammers, drops),
                     ("break_wall", d, r, b))

        # --- разбить кладку снизу (молоток) ---------------------------------
        blk = level.can_break_block(r, c, world)
        if blk and hammers >= 1:
            br, bc = blk
            push((cell, mask, world | {("block", br, bc)}, keys, hammers - 1, drops),
                 ("break_block", br, bc))

        # --- забрать ресурсы в текущей ячейке -------------------------------
        nworld, nkeys, nhammers, ndrops = pickup(world, [cell], keys, hammers, drops)
        if (nkeys, nhammers, ndrops) != (keys, hammers, drops):
            push((cell, mask, nworld, nkeys, nhammers, ndrops), ("pickup", r, c))

    if goal_state is None:
        return None

    plan = []
    s = goal_state
    while seen[s] is not None:
        prev, action = seen[s]
        plan.append(action)
        s = prev
    plan.reverse()
    _, _, _, keys_end, hammers_end, drops_end = goal_state
    return plan, keys_end, hammers_end, drops_end


def metrics(level, plan):
    """Метрики сложности по плану прохождения."""
    traps = dict(spikes=0, burning=0, shrink=0, sticky=0, slope=0)
    for r in range(ROWS):
        for c in range(COLS):
            if level.is_spike(r, c):
                traps["spikes"] += 1
            if level.is_burning(r, c):
                traps["burning"] += 1
            if level.is_shrink(r, c):
                traps["shrink"] += 1
            if level.is_sticky(r, c):
                traps["sticky"] += 1
            if level.is_slope(r, c):
                traps["slope"] += 1
    traps_total = sum(traps.values())

    # пройденные ячейки: собираем по действиям (для высокого прыжка — вся траектория)
    visited = [level.start]
    high_jumps = 0
    walls_broken = 0
    blocks_broken = 0
    for action in plan:
        kind = action[0]
        if kind == "hop":
            _, d, lr, lc = action
            visited.append((lr, lc))
        elif kind == "highjump":
            _, sr, d, lr, lc = action
            visited.append((sr, lc))
            visited.append((lr, lc))
            high_jumps += 1
        elif kind == "highjump_up":
            _, path = action
            visited.extend(path)
            high_jumps += 1
        elif kind == "break_wall":
            walls_broken += 1
        elif kind == "break_block":
            blocks_broken += 1

    traps_path = dict(spikes=0, burning=0, shrink=0, sticky=0, slope=0)
    no_rest = 0
    seen_cells = set()
    for cell in visited:
        if cell in seen_cells:
            continue
        seen_cells.add(cell)
        r, c = cell
        if level.is_spike(r, c):
            traps_path["spikes"] += 1
        if level.is_burning(r, c):
            traps_path["burning"] += 1
        if level.is_shrink(r, c):
            traps_path["shrink"] += 1
        if level.is_sticky(r, c):
            traps_path["sticky"] += 1
        if level.is_slope(r, c):
            traps_path["slope"] += 1
        # невозможность задержаться: ячейка, где rest_mode не «normal»/«locked»
        if level.rest_mode(r, c) in ("sticky", "slope"):
            no_rest += 1
        elif level.is_burning(r, c) or level.is_shrink(r, c):
            no_rest += 1

    traps_path_total = sum(traps_path.values())

    # обязательные одновременные действия: высокие прыжки (перестроение в полёте),
    # вынужденные отскоки с наклонных, скатывания с липких, ресурсные «замки»
    simultaneous = high_jumps + traps_path["slope"] + traps_path["sticky"]
    simultaneous += (1 if walls_broken else 0) + (1 if blocks_broken else 0)

    resources_required = walls_broken + blocks_broken
    moves = len(plan)

    score = (
        W_TRAPS * traps_total
        + W_TRAPS_PATH * traps_path_total
        + W_SIMULTANEOUS * simultaneous
        + W_NO_REST * no_rest
        + W_RESOURCES * resources_required
        + W_MOVES * moves
    )

    return dict(
        traps=traps,
        traps_total=traps_total,
        traps_path=traps_path,
        traps_path_total=traps_path_total,
        simultaneous=simultaneous,
        high_jumps=high_jumps,
        walls_broken=walls_broken,
        blocks_broken=blocks_broken,
        no_rest=no_rest,
        resources_required=resources_required,
        moves=moves,
        cells_visited=len(seen_cells),
        score=round(score, 3),
    )


def analyze_level(level, verbose=False, progress=None, res=(0, 0, 0)):
    solved = solve(level, verbose=verbose, res=res)
    if solved is None:
        result = dict(level=level.index, solvable=False, score=float("inf"),
                      plan=None, resources_end=res)
    else:
        plan, k_end, h_end, d_end = solved
        m = metrics(level, plan)
        m.update(level=level.index, solvable=True, resources_end=(k_end, h_end, d_end))
        if verbose:
            m["plan"] = [" ".join(str(x) for x in a) for a in plan]
        result = m
    if progress is not None:
        progress(level.index, result)
    return result


def playthrough(levels, verbose=False, progress=None):
    """Последовательное прохождение: снаряжение переносится между уровнями.

    Возвращает список результатов; если уровень нерешим с текущим карманом,
    прохождение останавливается (дальше без него игра непроходима).
    """
    results = []
    res = (0, 0, 0)
    for lv in levels:
        r = analyze_level(lv, verbose=verbose, progress=progress, res=res)
        results.append(r)
        if not r["solvable"]:
            break
        res = r["resources_end"]
    return results


def load_levels(path):
    with open(path, "r", encoding="utf-8") as fh:
        model = json.load(fh)
    return [Level(d) for d in model["levels"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("levels", nargs="?", default=DEFAULT_LEVELS, help="путь к levels.json")
    ap.add_argument("--level", type=int, default=None, help="разобрать один уровень")
    ap.add_argument("--verbose", action="store_true", help="печатать план прохождения")
    ap.add_argument("-o", "--json-out", default=DEFAULT_JSON_OUT, help="куда писать JSON-отчёт")
    ap.add_argument("-m", "--md-out", default=DEFAULT_MD_OUT, help="куда писать markdown-отчёт")
    ap.add_argument("-q", "--quiet", action="store_true", help="не печатать прогресс по уровням")
    args = ap.parse_args()

    levels = load_levels(args.levels)
    if args.level:
        levels = [lv for lv in levels if lv.index == args.level]
    total = len(levels)

    def search_progress(index, result):
        if args.quiet:
            return
        if result["solvable"]:
            tail = (f"score={result['score']:.1f} ловушки={result['traps_total']} "
                    f"одновр={result['simultaneous']} без-отд={result['no_rest']} "
                    f"ходов={result['moves']} карман={result['resources_end']}")
        else:
            tail = "НЕ РЕШЁН"
        print(f"[{index:>3}/{total}] уровень {index:>3}: {tail}", flush=True)

    if args.level:
        # одиночный уровень: считаем карман пустым (без переноса снаряжения)
        results = [analyze_level(levels[0], verbose=args.verbose,
                                 progress=search_progress)]
    else:
        results = playthrough(levels, verbose=args.verbose, progress=search_progress)

    solvable = [r for r in results if r["solvable"]]
    unsolvable = [r for r in results if not r["solvable"]]
    solvable.sort(key=lambda r: r["score"], reverse=True)

    print(f"уровней: {len(results)}, решено: {len(solvable)}, не решено: {len(unsolvable)}")
    if unsolvable:
        print("не решены:", ", ".join(str(r["level"]) for r in unsolvable))
    print()
    print(f"{'ранг':>4} {'ур.':>4} {'score':>7} {'ловуш':>6} {'одновр':>7} "
          f"{'без-отд':>8} {'снар':>5} {'ходов':>6}")
    for rank, r in enumerate(solvable, 1):
        print(f"{rank:>4} {r['level']:>4} {r['score']:>7.2f} {r['traps_total']:>6} "
              f"{r['simultaneous']:>7} {r['no_rest']:>8} {r['resources_required']:>5} "
              f"{r['moves']:>6}")

    out = {
        "weights": {
            "traps": W_TRAPS, "traps_path": W_TRAPS_PATH,
            "simultaneous": W_SIMULTANEOUS, "no_rest": W_NO_REST,
            "resources": W_RESOURCES, "moves": W_MOVES,
        },
        "solvable": len(solvable),
        "unsolvable": [r["level"] for r in unsolvable],
        "ranking": solvable,
    }
    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    lines = ["# Уровни Bumpy, отсортированные по сложности", ""]
    lines.append("Сложность = взвешенная сумма критериев:")
    lines.append("")
    lines.append("1. **ловушки** — шипы, горящие, сжимающиеся, липкие, наклонные платформы;")
    lines.append("2. **обязательные одновременные действия** — высокие прыжки с перестроением")
    lines.append("   в полёте, вынужденные отскоки с наклонных, скатывания с липких, ресурсные «замки»;")
    lines.append("3. **невозможность задержаться на месте** — ячейки плана, где шар не может")
    lines.append("   спокойно стоять (наклонные/липкие/сжимающиеся/горящие).")
    lines.append("")
    lines.append(f"Решено уровней: **{len(solvable)}** из {len(results)}."
                 + (f" Не решены: {', '.join(str(r['level']) for r in unsolvable)}." if unsolvable else ""))
    lines.append("")
    lines.append("| Ранг | Уровень | Сложность | Ловушки | На пути | Одновр. | Без отдыха | Снаряж. | Ходов |")
    lines.append("|-----:|--------:|----------:|--------:|--------:|--------:|-----------:|--------:|------:|")
    for rank, r in enumerate(solvable, 1):
        lines.append(
            f"| {rank} | {r['level']} | {r['score']:.2f} | {r['traps_total']} | "
            f"{r['traps_path_total']} | {r['simultaneous']} | {r['no_rest']} | "
            f"{r['resources_required']} | {r['moves']} |"
        )
    lines.append("")
    with open(args.md_out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print()
    print(f"записано: {args.json_out}")
    print(f"записано: {args.md_out}")


if __name__ == "__main__":
    main()
