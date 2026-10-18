#!/usr/bin/env python3
"""Решатель / планировщик прохождения уровней Bumpy.

По метаданным уровней из main/levels.json строит дискретную модель движения шара
и правил игровых элементов (зеркаля main/ball/ball.script, main/platforms/*,
main/walls/*) и ищет минимальную последовательность действий игрока, проходящую
уровень, вместе с минимальным набором предметов (drops / keys / hammers), которые
игрок должен иметь уже на старте, и списком предметов, реально потраченных планом.

Координаты экранные: row 0 — нижний ряд, col 0 — левая колонка. levels.json хранит
метаданные сверху вниз, поэтому row_meta переводится в row_screen = 5 - row_meta.

Модель (сознательная абстракция реальной непрерывной физики):

* Состояние покоя: шар пружинит на месте на твёрдой поверхности — на клетке
  платформы (row, col) или на вершине кирпичной кладки (блок в (row-1, col)).
* Боковой хоп (влево/вправо): сдвиг на одну колонку в текущем ряду. Блокируется
  вертикальной перегородкой (разрушаемая ломается за одно действие со стабильной
  опоры, тратя остаточную прочность в ключах) или кирпичной кладкой; иначе шар
  приземляется на первую поверхность на этом ряду или ниже.
* Высокий прыжок: поднимается до первого препятствия сверху в своей колонке. Во
  время подъёма на любом пройденном ряду игрок может отвести шар на одну колонку
  в сторону (те же правила блокировки), приземляясь на первую поверхность на этом
  ряду или ниже. На ряду самого препятствия отвод невозможен (шар останавливается
  чуть ниже него), поэтому для подъёма нужен свободный проход сверху. Обычный
  высокий прыжок возвращает шар в ту же клетку, но всё равно собирает предметы, через
  которые он пролетел.
* Наклонная платформа: приземление перенаправляется на одну клетку в сторону
  наклона (без управления игрока); наклон в край поля работает как обычная платформа.
* Липкая платформа: если удерживать прыжок в момент касания, шар начинает прыгать
  высоко повторно (авто-повтор), поэтому для планирования она ведёт себя как обычная
  платформа — в т.ч. кладка над ней ломается за одно действие. (Если кнопка отпущена,
  шар залипает и может только соскочить вбок, но удержание никогда не хуже, поэтому
  решатель предполагает, что игрок удерживает кнопку.) Вершина кладки ведёт себя как
  твёрдая, но запрещает высокий прыжок.
* Схлопывающаяся платформа: расходуется действием, которое с неё выполняют, а не
  приземлением, поэтому одноразовая платформа — это одна пусковая площадка: шар
  прыгает и платформа исчезает (любое дальнейшее приземление туда проваливается).
  Именно это позволяет шару, застрявшему на исчезающей платформе, упасть ниже.
* Опасные поверхности: шипы смертельны; горящие платформы расходуют одну каплю
  (иначе смерть).
* Кирпичную кладку и разрушаемую перегородку можно свести к одному действию только
  со СТАБИЛЬНОЙ платформы: игрок начинает бить и добивает её (один молоток для
  кладки, остаточная прочность в ключах для перегородки). Со СХЛОПЫВАЮЩЕЙСЯ платформы
  свёртка НЕЛЬЗЯ — шар берёт кладку по ряду / перегородку по удару, и каждое действие
  расходует использование платформы, поэтому платформа может исчезнуть, а шар упасть
  на поверхность ниже (и, возможно, проиграть). Кладку бьют снизу, перегородку сбоку.
* Коллектиблы (код объекта >= 5) открывают выход, как только собрано `timer` штук.
  Когда выход открывается, игра удаляет платформу в клетке выхода, поэтому клетка
  становится пустой; уровень завершён, как только шар коснулся таблички выхода, и это
  засчитывается даже на смертельном ходу.

Поиск: label-setting (лексикографический Дейкстра) по (состояние шара, мир) с
Pareto-фронтом недоминируемых меток (required, actions), поэтому состояния не
отсекаются лишь из-за того, что два вектора ресурсов имеют одинаковую сумму. Цель
лексикографическая: (1) меньше всего предметов на старте (min sum(required)),
(2) больше всего подобранных расходников по пути, (3) меньше всего действий игрока.
Очередь держит приоритет (суммарные предметы, actions + h), где h — максимум из двух
нижних оценок: обход колонок по интервалу и оптимистичная all-pairs дистанция,
игнорирующая опасности. (h недопустима в общем случае — цепочки наклонов двигают шар
на колонку бесплатно, а коллектиблы можно собрать пролётом, — поэтому она используется
только для упорядочивания, никогда для решения о корректности.) Подбор предметов
никогда не увеличивает стартовый запас, поэтому поиск вынужден исследовать все
состояния со стартовыми предметами не больше лучшей цели, прежде чем докажет максимум
собранного. Когда точный поиск упирается в лимит узлов, запускается жадный fallback
(кратчайший путь до следующего коллектибла + DFS по порядку сбора), который находит
план и помечается optimal=False.

Представление состояния: изменяемый мир упакован в небольшие целые (прочность стен и
остаток shrink — 2-битные поля, урон по кладке — 4-битные, набор блоков, потративших
молоток, и множества сожжённых/собранных клеток — битмаски), а пройденные клетки
хранятся 36-битной маской, что удешевляет хэширование и обновление мира.

Использование:
    python3 tools/solve_level.py --level 1
    python3 tools/solve_level.py --all --summary
    python3 tools/solve_level.py --all --json > solutions.json
    python3 tools/solve_level.py --level 6 --stats
"""

import argparse
import heapq
import json
import os
import sys
from collections import deque, namedtuple

COLS = 6
ROWS = 6
CELLS = COLS * ROWS
BLOCK_ROWS = 8  # main/walls/block/block.script go.property("rows", 8)

DEFAULT_LEVELS = os.path.join(os.path.dirname(__file__), "..", "main", "levels.json")

# коды lo-слоя -> вид платформы (см. main/level/level.script).
SHRINK = {2: 3, 3: 2, 4: 1}          # код -> оставшиеся использования
SLOPE = {6: -1, 7: 1}                # код -> направление наклона (сторона отскока)
BURNING = {8: "solid", 9: "sticky"}  # код -> поверхность после гашения каплей
BLOCK = 10
SPIKE = 12

# коды hi-слоя -> остаточная прочность (main/level/level.script WALL_DURABILITY)
WALL_DURA = {1: 1, 2: 2, 3: 3}

# коды объектов -> вид расходника (main/level/level.script goodie_factory)
OBJ_KIND = {1: "hammer", 2: "key", 3: "drop", 4: "life"}

RESOURCES = ("drop", "key", "hammer")
RES_INDEX = {name: i for i, name in enumerate(RESOURCES)}


def meta_cell_to_rc(cell):
    """Индекс клетки метаданных (row 0 = верх) -> (screen_row, col)."""
    return (ROWS - 1) - (cell // COLS), cell % COLS


def rc_bit(r, c):
    return 1 << (r * COLS + c)


def pack2(values):
    x = 0
    for i, v in enumerate(values):
        x |= (v & 3) << (2 * i)
    return x


# Изменяемая часть состояния уровня. Каждое поле — небольшое неизменяемое целое,
# чтобы World дёшево годился в качестве ключа словаря.
World = namedtuple("World", "walls shrink blocks burnt collected blockrows")


class Level:
    """Один уровень, разобранный из levels.json в экранно-ориентированные сетки.

    Также предвычисляет всё статичное, что нужно поиску: упакованные индексы
    изменяемых объектов, битмаски предметов и маски интервалов колонок.
    """

    def __init__(self, data):
        self.index = data["level"]
        self.theme = data.get("theme", 0)
        self.timer = data.get("timer", 0)
        self.start_r, self.start_c = meta_cell_to_rc(data["start_cell"])
        self.exit_r, self.exit_c = meta_cell_to_rc(data["timer_cell"])
        self.exit = (self.exit_r, self.exit_c)
        self.exit_bit = rc_bit(self.exit_r, self.exit_c)

        lo, hi, obj = data["grid_lo"], data["grid_hi"], data["objects"]

        self.plat = [[0] * COLS for _ in range(ROWS)]  # экранные ряды, row 0 = низ
        self.obj = [[0] * COLS for _ in range(ROWS)]
        for mr in range(ROWS):
            r = (ROWS - 1) - mr
            for c in range(COLS):
                self.plat[r][c] = lo[mr][c]
                self.obj[r][c] = obj[mr][c]

        # перегородки: колонка сетки gc — это граница b = gc + 1; борта неявные.
        self.walls = {}
        for mr in range(ROWS):
            r = (ROWS - 1) - mr
            for gc in range(COLS - 1):
                code = hi[mr][gc]
                if code:
                    self.walls[(r, gc + 1)] = code

        # упакованные индексы изменяемых объектов
        self.wall_index = {}
        self.wall_init = []
        for (rc, code) in sorted(self.walls.items()):
            if code in WALL_DURA:
                self.wall_index[rc] = len(self.wall_init)
                self.wall_init.append(WALL_DURA[code])
        self.wall_base = pack2(self.wall_init)

        self.shrink_index = {}
        self.shrink_init = []
        for r in range(ROWS):
            for c in range(COLS):
                if self.plat[r][c] in SHRINK:
                    self.shrink_index[(r, c)] = len(self.shrink_init)
                    self.shrink_init.append(SHRINK[self.plat[r][c]])
        self.shrink_base = pack2(self.shrink_init)

        self.block_index = {}
        for r in range(ROWS):
            for c in range(COLS):
                if self.plat[r][c] == BLOCK:
                    self.block_index[(r, c)] = len(self.block_index)

        # плоские таблицы поиска (чтобы не создавать tuple-ключи в горячих helpers)
        self.shrink_at = [-1] * CELLS
        for (r, c), idx in self.shrink_index.items():
            self.shrink_at[r * COLS + c] = idx
        self.block_at = [-1] * CELLS
        for (r, c), idx in self.block_index.items():
            self.block_at[r * COLS + c] = idx
        self.wall_at = [[-1] * (COLS + 1) for _ in range(ROWS)]
        for (r, b), idx in self.wall_index.items():
            self.wall_at[r][b] = idx

        # битмаски предметов
        self.drop_mask = self.key_mask = self.hammer_mask = 0
        self.collectible_mask = self.item_mask = 0
        for r in range(ROWS):
            for c in range(COLS):
                code = self.obj[r][c]
                if not code:
                    continue
                bit = rc_bit(r, c)
                self.item_mask |= bit
                if code == 3:
                    self.drop_mask |= bit
                elif code == 2:
                    self.key_mask |= bit
                elif code == 1:
                    self.hammer_mask |= bit
                elif code >= 5:
                    self.collectible_mask |= bit
        self.collectible_text = self.collectibles = self.collectible_mask.bit_count()

        # расходники, которые план может подобрать (drops / keys / hammers); жизни
        # (код 4) исключены — второй критерий считает только их
        self.consumable_mask = self.drop_mask | self.key_mask | self.hammer_mask
        self.consumable_count = self.consumable_mask.bit_count()

        # маски интервалов колонок: col_range[c][lo][hi] = биты рядов lo..hi в колонке c
        self.col_range = [[[0] * ROWS for _ in range(ROWS)] for _ in range(COLS)]
        for c in range(COLS):
            for lo in range(ROWS):
                for hi in range(lo, ROWS):
                    m = 0
                    for r in range(lo, hi + 1):
                        m |= rc_bit(r, c)
                    self.col_range[c][lo][hi] = m

        self._build_opt_dist()

    def _build_opt_dist(self):
        """Оптимистичные all-pairs дистанции в действиях между клетками.

        Оптимистичный граф убирает все опасности (стены, кладки, шипы, shrink,
        горящие, удаление выхода) и считает любую платформу безопасным полом,
        поэтому его расстояние — нижняя оценка реальных усилий (используется как
        эвристика). Дистанции в действиях между индексами клеток r*6+c.
        """
        floor = [[self.plat[r][c] != 0 for c in range(COLS)] for r in range(ROWS)]

        def neighbors(r, c):
            res = []

            def land(c2, from_row):
                for r2 in range(from_row, -1, -1):
                    if floor[r2][c2]:
                        res.append(r2 * COLS + c2)
                        return

            for d in (-1, 1):
                c2 = c + d
                if 0 <= c2 < COLS:
                    land(c2, r)
            obs = None
            for rr in range(r + 1, ROWS):
                if floor[rr][c]:
                    obs = rr
                    break
            rr_max = (obs - 1) if obs is not None else ROWS - 1
            for rr in range(r + 1, rr_max + 1):
                for d in (-1, 1):
                    c2 = c + d
                    if 0 <= c2 < COLS:
                        land(c2, rr)
            return res

        big = 10 ** 9
        dist = [[big] * CELLS for _ in range(CELLS)]
        for s in range(CELLS):
            sr, sc = divmod(s, COLS)
            dist[s][s] = 0
            dq = deque([(sr, sc)])
            while dq:
                r, c = dq.popleft()
                base = r * COLS + c
                dd = dist[s][base]
                for idx in neighbors(r, c):
                    if dist[s][idx] == big:
                        dist[s][idx] = dd + 1
                        dq.append((idx // COLS, idx % COLS))
        self.opt_dist = dist
        self.opt_big = big

    def initial_world(self):
        return World(self.wall_base, self.shrink_base, 0, 0, 0, 0)

    # -- статические запросы -----------------------------------------------

    def wall_code(self, r, b):
        return self.walls.get((r, b), 0)

    def has_block(self, r, c):
        return 0 <= r < ROWS and self.plat[r][c] == BLOCK


# -- helpers упакованного мира ---------------------------------------------

def wall_remaining(level, r, b, world):
    """Остаточная прочность: -1 если разрушаемой перегородки нет, иначе 0..3."""
    idx = level.wall_at[r][b]
    if idx < 0:
        return -1
    return (world.walls >> (2 * idx)) & 3


def wall_set(level, world, r, b, value):
    idx = level.wall_at[r][b]
    if idx < 0:
        return world
    shift = 2 * idx
    mask = 3 << shift
    return world._replace(walls=(world.walls & ~mask) | ((value & 3) << shift))


def wall_hit(level, world, r, b):
    return wall_set(level, world, r, b, max(0, wall_remaining(level, r, b, world) - 1))


def wall_destroy(level, world, r, b):
    return wall_set(level, world, r, b, 0)


def block_broken(level, r, c, world):
    """Сколько рядов кирпичной кладки уже выбито (0..BLOCK_ROWS)."""
    idx = level.block_at[r * COLS + c]
    if idx < 0:
        return 0
    return (world.blockrows >> (4 * idx)) & 0xF


def block_destroyed(level, r, c, world):
    return block_broken(level, r, c, world) >= BLOCK_ROWS


def _block_set_rows(level, world, r, c, rows):
    idx = level.block_at[r * COLS + c]
    if idx < 0:
        return world
    shift = 4 * idx
    rows = max(0, min(BLOCK_ROWS, rows))
    # `blocks` помечает каждый блок, потративший молоток (хотя бы один удар)
    return world._replace(
        blockrows=(world.blockrows & ~(0xF << shift)) | (rows << shift),
        blocks=world.blocks | (1 << idx))


def block_hit(level, world, r, c):
    """Один удар снизу: выбивает один ряд кладки."""
    return _block_set_rows(level, world, r, c,
                           block_broken(level, r, c, world) + 1)


def block_destroy(level, world, r, c):
    return _block_set_rows(level, world, r, c, BLOCK_ROWS)


def shrink_remaining(level, r, c, world):
    idx = level.shrink_at[r * COLS + c]
    if idx < 0:
        return 0
    return (world.shrink >> (2 * idx)) & 3


def shrink_dec(level, world, r, c):
    idx = level.shrink_at[r * COLS + c]
    if idx < 0:
        return world
    shift = 2 * idx
    value = max(0, ((world.shrink >> shift) & 3) - 1)
    mask = 3 << shift
    return world._replace(shrink=(world.shrink & ~mask) | (value << shift))


def extinguish(level, world, r, c):
    return world._replace(burnt=world.burnt | rc_bit(r, c))


def collected_collectibles(level, world):
    return (world.collected & level.collectible_mask).bit_count()


def collected_items(level, world):
    """Число расходников (drops / keys / hammers), подобранных шаром."""
    return (world.collected & level.consumable_mask).bit_count()


def exit_opened(level, world):
    return (level.timer <= 0
            or (world.collected & level.collectible_mask).bit_count() >= level.timer)


def collect_items(level, world, cells):
    """Добавляет клетки с предметами среди пройденных `cells`."""
    add = cells & level.item_mask
    if not add or (add & ~world.collected) == 0:
        return world
    return world._replace(collected=world.collected | add)


def keys_used(level, world):
    used = 0
    w = world.walls
    for i, init in enumerate(level.wall_init):
        used += init - ((w >> (2 * i)) & 3)
    return used


def inventory(level, world, required):
    """Доступные количества по ресурсам = собрано - потрачено + занято в долг."""
    drops = (world.collected & level.drop_mask).bit_count() - world.burnt.bit_count() + required[0]
    keys = (world.collected & level.key_mask).bit_count() - keys_used(level, world) + required[1]
    hammers = (world.collected & level.hammer_mask).bit_count() - world.blocks.bit_count() + required[2]
    return (drops, keys, hammers)


def spend(level, world, required, resource, n=1):
    """Тратит `n` единиц `resource`, при нехватке занимая в долг (растёт `required`)."""
    have = inventory(level, world, required)[RES_INDEX[resource]]
    if have >= n:
        return required
    req = list(required)
    req[RES_INDEX[resource]] += n - have
    return tuple(req)


def consumed_items(level, world):
    """Реально потраченные планом предметы в виде (drops, keys, hammers)."""
    return (world.burnt.bit_count(), keys_used(level, world), world.blocks.bit_count())


# -- модель движения -------------------------------------------------------

def floor_at(level, r, c, world):
    """Поверхность, которую шар видит, опускаясь в (r, c), или None если пусто.

    Возвращает одно из: ('solid',), ('sticky',), ('slope', dir), ('spike',),
    ('burn', surface_after), ('shrink',), ('blocktop',).
    """
    if r < 0 or r >= ROWS:
        return None
    # платформа в клетке выхода удаляется при открытии выхода, поэтому клетка
    # становится пустой и шар проваливается сквозь неё (касание таблички важнее)
    if (r, c) == level.exit and exit_opened(level, world):
        return None
    code = level.plat[r][c]
    if code in SHRINK:
        return ("shrink",) if shrink_remaining(level, r, c, world) > 0 else None
    if code == 1:
        return ("solid",)
    if code == 5:
        return ("sticky",)
    if code in SLOPE:
        return ("slope", SLOPE[code])
    if code in BURNING:
        if (world.burnt >> (r * COLS + c)) & 1:
            return ("sticky",) if BURNING[code] == "sticky" else ("solid",)
        return ("burn", BURNING[code])
    if code == SPIKE:
        return ("spike",)
    if code == BLOCK:
        return None  # кладка занимает эту клетку; её вершина на r+1
    if r >= 1 and level.has_block(r - 1, c) and not block_destroyed(level, r - 1, c, world):
        return ("blocktop",)
    return None


def landing(level, c, start_row, world, required, depth=0):
    """Шар опускается в колонке c начиная с `start_row`.

    Возвращает (outcome, cells_mask): `outcome` — (r, c, kind, world, required)
    с kind из {'plat','blocktop'}, или None если шар погиб (шипы / падение за
    пределы поля); `cells_mask` помечает все пройденные клетки, что важно, т.к.
    касание таблички выхода выигрывает даже на смертельном ходу.
    """
    r = start_row
    while r >= 0:
        f = floor_at(level, r, c, world)
        if f is None:
            r -= 1
            continue
        kind = f[0]
        span = level.col_range[c][r][start_row]
        if kind == "spike":
            return None, level.col_range[c][0][start_row]
        if kind == "shrink":
            return (r, c, "plat", world, required), span
        if kind == "burn":
            required = spend(level, world, required, "drop")
            return (r, c, "plat", extinguish(level, world, r, c), required), span
        if kind == "slope":
            d = f[1]
            if not (0 <= c + d < COLS) or depth > 16:
                return (r, c, "plat", world, required), span
            out, cells = lateral(level, r, c, d, world, required, depth=depth + 1)
            return out, cells | span
        if kind == "blocktop":
            return (r, c, "blocktop", world, required), span
        return (r, c, "plat", world, required), span
    return None, level.col_range[c][0][start_row]


def lateral(level, r, c, d, world, required, depth=0):
    """Шар прыгает из (r, c) на одну колонку в направлении d и приземляется.

    Блокирующая перегородка стоит свою прочность в ключах (если разрушаемая) и
    отбрасывает шар назад; кладка тоже отбрасывает. Возвращает (outcome, cells_mask).
    """
    c2 = c + d
    if not (0 <= c2 < COLS):
        return (r, c, "plat", world, required), rc_bit(r, c)
    b = max(c, c2)
    rem = wall_remaining(level, r, b, world)
    if rem > 0:
        required = spend(level, world, required, "key")
        return (r, c, "plat", wall_hit(level, world, r, b), required), rc_bit(r, c)
    if rem == -1 and level.wall_code(r, b) != 0:
        return (r, c, "plat", world, required), rc_bit(r, c)
    if level.has_block(r, c2) and not block_destroyed(level, r, c2, world):
        return (r, c, "plat", world, required), rc_bit(r, c)
    out, cells = landing(level, c2, r, world, required, depth=depth)
    return out, cells | rc_bit(r, c)


def obstacle_above(level, r, c, world):
    """Нижайшее препятствие выше (r, c): возвращает (row, kind) или (None, None)."""
    for rr in range(r + 1, ROWS):
        if level.has_block(rr, c) and not block_destroyed(level, rr, c, world):
            return rr, "block"
        code = level.plat[rr][c]
        if code and code != BLOCK:
            if code in SHRINK and shrink_remaining(level, rr, c, world) <= 0:
                continue
            if (rr, c) == level.exit and exit_opened(level, world):
                continue  # платформа в клетке выхода удалена
            return rr, "platform"
    return None, None


def successors(level, state, world, required):
    """Список (new_state, new_world, new_required, label, cells, cost).

    `cells` — 36-битная маска всех клеток, которые шар занимает или проходит за
    действие. `cost` — сколько действий игрока это стоит.

    Опора на схлопывающейся платформе — это тот отскок, на котором действует
    игрок: действие расходует одно использование платформы, поэтому одноразовая
    платформа исчезает сразу после первого прыжка (любое действие, остающееся в
    клетке, после этого падает).
    """
    r, c, kind = state
    out = []
    rest_shrink = kind != "blocktop" and level.plat[r][c] in SHRINK
    rest_bit = rc_bit(r, c)

    # ---- высокий прыжок ---------------------------------------------------
    # запрещён только на вершине кладки. Липкая платформа для планирования ведёт
    # себя как обычная: удержание прыжка в момент касания даёт повторные высокие
    # прыжки (и авто-повтор, поэтому кладка над ней ломается за одно действие);
    # при отпущенной кнопке шар бы залип, но игрок всегда может удерживать, что
    # никогда не хуже.
    if kind != "blocktop":
        obs_r, obs_kind = obstacle_above(level, r, c, world)
        rr_max = (obs_r - 1) if obs_r is not None else ROWS - 1
        reach = list(range(r + 1, rr_max + 1))
        hi_cells = rest_bit | (level.col_range[c][r + 1][rr_max] if reach else 0)

        # высокий прыжок возможен всегда: когда сверху пусто, шар поднимается и
        # возвращается в ту же клетку, собирая предметы, через которые пролетел
        out.append(((r, c, kind), world, required,
                    f"high jump in place at ({r},{c})", hi_cells, 1))

        # удар по кирпичной кладке прямо сверху. Со СТАБИЛЬНОЙ платформы игрок
        # начинает бить и добивает кладку за одно действие (один молоток): там
        # обрушить её целиком безопасно. Со СХЛОПЫВАЮЩЕЙСЯ платформы свёртка
        # невозможна — действие выбивает один ряд и тратит одно использование
        # платформы, поэтому платформа может исчезнуть, шар упадёт на следующую
        # поверхность ниже и продолжит бить оттуда (и может просто проиграть).
        if obs_kind == "block":
            first = block_broken(level, obs_r, c, world) == 0
            req2 = spend(level, world, required, "hammer") if first else required
            if rest_shrink:
                w2 = block_hit(level, world, obs_r, c)
                done = block_broken(level, obs_r, c, w2)
                label = (f"hit block ({obs_r},{c}) from below "
                         f"({done}/{BLOCK_ROWS} rows"
                         f"{', uses 1 hammer' if first else ''})")
            else:
                w2 = block_destroy(level, world, obs_r, c)
                label = (f"break block ({obs_r},{c}) from below"
                         f"{' (uses 1 hammer)' if first else ''}")
            out.append(((r, c, kind), w2, req2, label,
                        rest_bit | level.col_range[c][r + 1][obs_r - 1],
                        1))

        # отвод на одну колонку на каждом достижимом ряду
        for rr in reach:
            rise = rest_bit | level.col_range[c][r + 1][rr]
            for d in (-1, 1):
                c2 = c + d
                if not (0 <= c2 < COLS):
                    continue
                b = max(c, c2)
                rem = wall_remaining(level, rr, b, world)
                if rem > 0:
                    req2 = spend(level, world, required, "key", rem)
                    cost = rem if rest_shrink else 1
                    out.append(((r, c, kind), wall_destroy(level, world, rr, b), req2,
                                f"high jump, break wall {b} at row {rr} ({rem} keys)",
                                rise, cost))
                    continue
                if rem == -1 and level.wall_code(rr, b) != 0:
                    continue
                if level.has_block(rr, c2) and not block_destroyed(level, rr, c2, world):
                    continue
                out2, lcells = landing(level, c2, rr, world, required)
                cells = rise | lcells
                if out2 is None:
                    out.append((("DEAD", 0, 0), world, required,
                                f"high jump, divert to column {c2} (fatal)", cells, 1))
                    continue
                r2, c2r, k2, w2, req2 = out2
                out.append(((r2, c2r, k2), w2, req2,
                            f"high jump, divert to ({r2},{c2r})", cells, 1))

    # ---- боковой хоп ------------------------------------------------------
    for d in (-1, 1):
        c2 = c + d
        if not (0 <= c2 < COLS):
            continue
        b = max(c, c2)
        rem = wall_remaining(level, r, b, world)
        if rem > 0:  # разрушаемая перегородка: со стабильной платформы одно действие
            req2 = spend(level, world, required, "key", rem)
            cost = rem if rest_shrink else 1
            out.append(((r, c, kind), wall_destroy(level, world, r, b), req2,
                        f"break wall {b} at row {r} ({rem} keys)", rest_bit, cost))
            continue
        if rem == -1 and level.wall_code(r, b) != 0:
            if rest_shrink:
                out.append(((r, c, kind), world, required,
                            f"bounce off wall {b} at row {r}", rest_bit, 1))
            continue
        if level.has_block(r, c2) and not block_destroyed(level, r, c2, world):
            if rest_shrink:
                out.append(((r, c, kind), world, required,
                            f"bounce off block ({r},{c2})", rest_bit, 1))
            continue
        res, lcells = lateral(level, r, c, d, world, required)
        cells = lcells | rest_bit
        if res is None:
            out.append((("DEAD", 0, 0), world, required,
                        f"hop to column {c2} (fatal)", cells, 1))
            continue
        r2, c2r, k2, w2, req2 = res
        if r2 == r and c2r == c:
            # результат в той же клетке всё же может собрать предметы, через
            # которые шар пролетел (например, наклон отбросил его назад через
            # угловую клетку), или потратить ресурс; настоящий no-op позже
            # отсекается доминированием меток.
            out.append(((r, c, kind), w2, req2,
                        f"hop from ({r},{c}) and return via column {c2}", cells, 1))
        else:
            out.append(((r2, c2r, k2), w2, req2,
                        f"hop ({r},{c}) -> ({r2},{c2r})", cells, 1))

    # расходуем одно использование схлопывающейся опоры за действие; если оно её
    # опустошило, а действие не покинуло клетку, шар теперь проваливается
    if rest_shrink:
        consumed = []
        for ns, nw, nreq, label, cells, cost in out:
            nw2 = shrink_dec(level, nw, r, c)
            if ns[0] != "DEAD" and ns[0] != "GOAL" and (ns[0], ns[1]) == (r, c) \
                    and shrink_remaining(level, r, c, nw2) <= 0:
                fell, fcells = landing(level, c, r - 1, nw2, nreq)
                if fell is None:
                    # шар падает за пределы поля / на шипы после исчезновения
                    # платформы; оставляем переход смертельным, чтобы касание
                    # выхода по пути всё равно было замечено
                    consumed.append((("DEAD", 0, 0), nw2, nreq,
                                     label + ", platform vanishes and falls off",
                                     cells | fcells, cost))
                    continue
                r2, c2b, k2, w3, req3 = fell
                consumed.append(((r2, c2b, k2), w3, req3,
                                 label + ", platform vanishes and falls",
                                 cells | fcells | level.col_range[c][r2][r], cost))
            else:
                consumed.append((ns, nw2, nreq, label, cells, cost))
        out = consumed

    # опора, оставшаяся на исчезнувшей схлопывающейся платформе, не может стоять
    if kind != "blocktop" and floor_at(level, r, c, world) is None:
        out = [s for s in out if s[0][0] == "DEAD" or s[0][0] == "GOAL"
               or (s[0][0], s[0][1]) != (r, c)]

    return out


def start_state_of(level, world, required):
    """Состояние покоя шара на спавне уровня (отражает первые кадры игры).

    Возвращает (state, world, required) или None, если шар погибает на спавне.
    Обрабатывает спавн на липкой платформе (касание с одним действием) и на
    наклонной (шар сразу сносит на клетку в сторону наклона без действия игрока),
    помимо обычной опоры или падения.
    """
    r, c = level.start_r, level.start_c
    f = floor_at(level, r, c, world)
    if f is None:
        fell, _cells = landing(level, c, r - 1, world, required)
        if fell is None:
            return None
        return (fell[0], fell[1], fell[2]), fell[3], fell[4]
    if f[0] == "slope":
        out, _cells = lateral(level, r, c, f[1], world, required)
        if out is None:
            return None
        return (out[0], out[1], out[2]), out[3], out[4]
    if f[0] == "blocktop":
        return (r, c, "blocktop"), world, required
    return (r, c, "plat"), world, required


def nw_or(nw):
    return nw


# -- поиск -----------------------------------------------------------------

def _path_from(nodes, nid):
    labels = []
    n = nid
    while n is not None:
        if nodes[n][3] is not None:
            labels.append(nodes[n][3])
        n = nodes[n][4]
    labels.reverse()
    return nodes[nid][0], nodes[nid][1], nodes[nid][2], labels


def _reach_phase(level, start_state, start_world, req0, edge_goal, cap):
    """Дейкстра (по действиям) до первого хода, удовлетворяющего `edge_goal`.

    `edge_goal(cells, world)` задаёт цель фазы. Ресурсы игнорируются (занимать в
    долг бесплатно), а состояния дедуплицируются по (state, world) с сохранением
    самого дешёвого, чего достаточно, чтобы найти короткий путь. Возвращает
    (state, world, required, labels) или None.
    """
    nodes = [(start_state, start_world, req0, None, None)]
    best = {(start_state, start_world): 0}
    pq = [(0, 0)]
    while pq:
        acts, nid = heapq.heappop(pq)
        state, world, req, _lab, _par = nodes[nid]
        if best.get((state, world), 1 << 30) < acts:
            continue
        for ns, nw, nreq, label, cells, cost in successors(level, state, world, req):
            nw2 = collect_items(level, nw, cells)
            if edge_goal(cells, nw2, ns):
                nodes.append((ns, nw2, nreq, label, nid))
                return _path_from(nodes, len(nodes) - 1)
            if ns[0] == "DEAD":
                continue
            key = (ns, nw2)
            nacts = acts + cost
            if best.get(key, 1 << 30) <= nacts:
                continue
            best[key] = nacts
            nodes.append((ns, nw2, nreq, label, nid))
            heapq.heappush(pq, (nacts, len(nodes) - 1))
            if len(nodes) > cap:
                return None
    return None


def _phase_greedy(level, phase_cap=400000, max_phases=64):
    """Жадный fallback: повторно берёт кратчайший путь до любого оставшегося
    коллектибла, затем до выхода. Быстро; возвращает (actions, required, used,
    actions_count, collected) или None."""
    start_state = (level.start_r, level.start_c, "plat")
    world = collect_items(level, level.initial_world(),
                          rc_bit(level.start_r, level.start_c))
    req = (0, 0, 0)
    st0 = start_state_of(level, world, req)
    if st0 is None:
        return None
    start_state, world, req = st0

    remaining = level.collectible_mask & ~world.collected
    state, path = start_state, []
    for _ in range(max_phases):
        if not remaining:
            break
        goal = (lambda cells, w, ns: ns[0] != "DEAD" and (cells & remaining) != 0)
        res = _reach_phase(level, state, world, req, goal, phase_cap)
        if res is None:
            return None
        state, world, req, labels = res
        path += labels
        remaining &= ~world.collected
    if remaining:
        return None
    goal = (lambda cells, w, ns: exit_opened(level, w) and (cells & level.exit_bit) != 0)
    res = _reach_phase(level, state, world, req, goal, phase_cap)
    if res is None:
        return None
    state, world, req, labels = res
    path += labels
    return (path, req, consumed_items(level, world), len(path),
            collected_items(level, world))


def greedy_plan(level, phase_cap=400000, max_depth=24, max_phases=4000):
    """Находит план, сцепляя короткие поиски до коллектиблов и выхода.

    Поиск в глубину по порядку сбора коллектиблов; каждое ребро — кратчайший путь
    до одного коллектибла / выхода, найденный через `_reach_phase`. Быстро, но
    минимальность не доказана: используется как fallback, когда точный поиск
    упёрся в лимит узлов. Возвращает (actions, required, used, actions_count,
    collected) или None.
    """
    start_state = (level.start_r, level.start_c, "plat")
    world = collect_items(level, level.initial_world(),
                          rc_bit(level.start_r, level.start_c))
    req = (0, 0, 0)
    st0 = start_state_of(level, world, req)
    if st0 is None:
        return None
    start_state, world, req = st0

    remaining = level.collectible_mask & ~world.collected
    D = level.opt_dist
    memo = set()
    calls = [0]

    def dfs(state, world, req, remaining, depth):
        if depth > max_depth:
            return None
        if not remaining:
            goal = (lambda cells, w, ns:
                    exit_opened(level, w) and (cells & level.exit_bit) != 0)
            calls[0] += 1
            res = _reach_phase(level, state, world, req, goal, phase_cap)
            if res is None:
                return None
            return res[3], res[1], res[2]
        key = (state, world)
        if key in memo:
            return None
        cur = state[0] * COLS + state[1]
        targets = sorted((t for t in range(CELLS) if (remaining >> t) & 1),
                         key=lambda t: D[cur][t])
        for t in targets:
            bit = 1 << t
            goal = (lambda cells, w, ns, b=bit: ns[0] != "DEAD" and (cells & b) != 0)
            calls[0] += 1
            if calls[0] > max_phases:
                return None
            res = _reach_phase(level, state, world, req, goal, phase_cap)
            if res is None:
                continue
            nstate, nworld, nreq, labels = res
            sub = dfs(nstate, nworld, nreq, remaining & ~nworld.collected, depth + 1)
            if sub is not None:
                slabels, fworld, freq = sub
                return labels + slabels, fworld, freq
        memo.add(key)
        return None

    out = dfs(start_state, world, req, remaining, 0)
    if out is None:
        return None
    labels, fworld, freq = out
    return (labels, freq, consumed_items(level, fworld), len(labels),
            collected_items(level, fworld))


def is_solvable(level, node_cap=400000):
    """Быстрый оракул решаемости для генераторов уровней.

    Останавливается на первом найденном плане (без доказательства оптимальности
    и без поиска максимума сбора) и, когда точный поиск упирается в лимит узлов,
    всё равно пробует жадный fallback и «последнюю надежду», чтобы проходимый
    уровень не был ложно назван нерешаемым.

    Возвращает статус с тройным смыслом: "solvable" (план найден), "impossible"
    (исчерпывающе нет плана) или "limit" (уперлись в лимит до решения).
    Генераторам следует отбрасывать только "impossible", а "limit" — повторять
    с большим лимитом.
    """
    return solve(level, node_cap=node_cap, legacy=True,
                 allow_fallback=True).get("status")


def solve(level, node_cap=400000, stats=None, greedy=False, allow_fallback=True,
          legacy=False):
    """Ищет минимальный план (см. docstring модуля).

    Возвращает словарь: status из {'solvable','impossible','limit'}, reason,
    actions (упорядоченные подписи), required (предметы на старте), used (реально
    потраченные), collected (подобранные расходники) и items (расходников на
    уровне), nodes, optimal (True, когда минимальность доказана) и (если передан
    словарь `stats`) счётчики поиска.

    Когда точный лексикографический поиск упирается в `node_cap`, запускается
    жадный best-first fallback (`allow_fallback`), который находит *какой-то*
    план без доказательства минимальности, поэтому каждый проходимый уровень всё
    равно даёт прохождение; результат тогда помечается optimal=False.
    """
    st = stats if stats is not None else {}
    st.update(popped=0, transitions=0, unique_keys=0, labels=0,
              dominance_hits=0, peak_queue=0, peak_labels=0, peak_front=0,
              bound_prunes=0, finished="")

    if level.timer > level.collectibles:
        st["finished"] = "bad_metadata"
        return {"status": "impossible",
                "reason": "fewer collectibles on the level than the exit needs",
                "actions": [], "required": (0, 0, 0), "used": (0, 0, 0),
                "nodes": 0, "stats": st}

    start_world = collect_items(level, level.initial_world(),
                                rc_bit(level.start_r, level.start_c))
    req0 = (0, 0, 0)
    # опора на спавне: обычная, липкое касание, отскок по наклону или падение,
    # если у стартовой клетки нет поверхности
    st0 = start_state_of(level, start_world, req0)
    if st0 is None:
        st["finished"] = "start_fall"
        return {"status": "impossible", "reason": "ball falls off at start",
                "actions": [], "required": req0, "used": (0, 0, 0),
                "nodes": 0, "stats": st}
    start_state, start_world, req0 = st0

    hcache = {}

    def heuristic(state, world):
        # Допустимая нижняя оценка остатка действий по оптимистичной all-pairs
        # матрице (стены/кладки/шипы/shrink игнорируются). Шар должен достичь
        # выхода и каждого оставшегося коллектибла; для любой такой цели t путь
        # current -> t -> exit стоит минимум d(cur,t)+d(t,exit), а весь путь —
        # минимум d(cur,exit).
        # Замечание: в общем случае доказуемо НЕ допустима (цепочки наклонов
        # двигают шар на колонку бесплатно, а коллектиблы можно собрать
        # пролётом), поэтому используется только для упорядочивания, никогда для
        # решения о корректности.
        if state[0] == "GOAL":
            return 0
        cur = state[0] * COLS + state[1]
        rem = level.collectible_mask & ~world.collected
        key = (cur, rem)
        cached = hcache.get(key)
        if cached is not None:
            return cached
        D = level.opt_dist
        big = level.opt_big
        e = level.exit_r * COLS + level.exit_c
        # оценка 2: оптимистичная all-pairs дистанция; нужно достичь выхода и
        # каждого оставшегося коллектибла t, поэтому путь >= d(cur,exit) и
        # >= d(cur,t)+d(t,exit)
        base = D[cur][e]
        best = base if base < big else 0
        m = rem
        while m:
            bit = m & -m
            t = bit.bit_length() - 1
            m ^= bit
            dt = D[cur][t] + D[t][e]
            if dt < big and dt > best:
                best = dt
        # оценка 1: обход по интервалу колонок (одна колонка за действие, ряды бесплатны)
        ec = level.exit_c
        a = b = ec
        for c2 in range(COLS):
            if rem & level.col_range[c2][0][ROWS - 1]:
                if c2 < a:
                    a = c2
                if c2 > b:
                    b = c2
        c = state[1]
        d1 = abs(c - a) + (b - a) + (b - ec)
        d2 = abs(c - b) + (b - a) + (ec - a)
        colb = d1 if d1 < d2 else d2
        val = best if best > colb else colb
        hcache[key] = val
        return val

    labels = {}   # (state, world) -> список недоминируемых (required, actions)
    nodes = []    # (state, world, required, action_label, parent_id)
    pq = []       # (sum(required), actions + h, actions, node_id)

    def add_label(key, required, actions, node):
        lst = labels.get(key)
        if greedy:
            # fallback по достижимости: оставляем только самую дешёвую метку на ключ
            if lst is not None and lst[0][1] <= actions:
                st["dominance_hits"] += 1
                return
        elif lst is not None:
            for lab in lst:
                if (lab[0][0] <= required[0] and lab[0][1] <= required[1]
                        and lab[0][2] <= required[2] and lab[1] <= actions):
                    st["dominance_hits"] += 1
                    return
            kept = [lab for lab in lst
                    if not (required[0] <= lab[0][0] and required[1] <= lab[0][1]
                            and required[2] <= lab[0][2] and actions <= lab[1])]
            st["labels"] -= len(lst) - len(kept)
            lst = kept
        if lst is None:
            st["unique_keys"] += 1
            lst = []
        lst.append((required, actions))
        labels[key] = lst
        nodes.append(node)
        st["labels"] += 1
        if st["labels"] > st["peak_labels"]:
            st["peak_labels"] = st["labels"]
        if len(lst) > st["peak_front"]:
            st["peak_front"] = len(lst)
        h = heuristic(key[0], key[1])
        if greedy:
            rem = (level.collectible_mask & ~key[1].collected).bit_count()
            heapq.heappush(pq, (h, rem, actions, len(nodes) - 1))
        else:
            heapq.heappush(pq, (sum(required), actions + h, actions, len(nodes) - 1))

    add_label((start_state, start_world), req0, 0,
              (start_state, start_world, req0, None, None))

    goal_id = None
    best_goal = None      # (sum required, -collected, actions) лучшей цели
    best_goal_nid = None
    limit_hit = False

    def record_goal(nid, world, required, actions):
        """Отслеживает лексикографически лучшую цель, увиденную до сих пор.

        Значение цели — (предметы на старте, -собранные расходники, действия):
        план должен сначала требовать меньше всего предметов на старте, затем
        подобрать как можно больше расходников, затем использовать меньше действий.
        """
        nonlocal best_goal, best_goal_nid
        cand = (sum(required), -collected_items(level, world), actions)
        if best_goal is None or cand < best_goal:
            best_goal = cand
            best_goal_nid = nid

    def build_result(nid, optimal):
        world = nodes[nid][1]
        path = []
        n = nid
        while n is not None:
            if nodes[n][3] is not None:
                path.append(nodes[n][3])
            n = nodes[n][4]
        path.reverse()
        return {"status": "solvable",
                "reason": "" if optimal else "minimality not proven (node cap)",
                "actions": path, "required": nodes[nid][2],
                "used": consumed_items(level, world),
                "collected": collected_items(level, world),
                "items": level.consumable_count,
                "nodes": len(nodes), "optimal": optimal, "stats": st}

    while pq:
        _summ, _f, actions, nid = heapq.heappop(pq)
        # подбор предметов никогда не увеличивает стартовый запас, поэтому как
        # только цель известна, любое состояние, у которого сумма required уже
        # превышает сумму у лучшей цели, не может улучшить первый критерий; куча
        # упорядочена по этой сумме, значит и все оставшиеся состояния бесполезны.
        # В legacy-режиме нужен лишь план (без оптимальности), поэтому возвращается
        # первая цель.
        if not greedy and not legacy and best_goal is not None and _summ > best_goal[0]:
            st["finished"] = "proved"
            break
        state, world, required, _label, _parent = nodes[nid]
        st["popped"] += 1
        if len(pq) > st["peak_queue"]:
            st["peak_queue"] = len(pq)

        stale = False
        for lab in labels.get((state, world), ()):
            if (lab != (required, actions)
                    and lab[0][0] <= required[0] and lab[0][1] <= required[1]
                    and lab[0][2] <= required[2] and lab[1] <= actions):
                stale = True
                break
        if stale:
            continue

        # граница оптимальности по второму/третьему критерию. Заявленная граница
        # «собрано сейчас + всё ещё несобранное» всегда равна общему числу
        # расходников уровня, поэтому сама по себе вакуумна. Она срабатывает лишь
        # когда лучший план уже собрал максимум возможного: тогда ни одно
        # продолжение не улучшит collected, первый критерий зафиксирован, и
        # состояние, у которого собственное число действий уже превышает лучшую
        # цель, не может её побить. (Используется только `actions`, никогда
        # `actions + h`: эвристика служит лишь упорядочиванию и не доказана
        # допустимой, поэтому не должна управлять решением о корректности.)
        if (not greedy and not legacy and best_goal is not None
                and _summ == best_goal[0]
                and -best_goal[1] == level.consumable_count
                and actions > best_goal[2]):
            st["bound_prunes"] += 1
            continue

        if greedy:
            if state[0] == "GOAL" or (state[0] != "GOAL" and exit_opened(level, world)
                                      and (state[0], state[1]) == level.exit):
                goal_id = nid
                st["finished"] = "goal"
                break
        elif exit_opened(level, world) and (state[0], state[1]) == level.exit:
            # шар уже стоит на открытом выходе (например, открыл выход из соседней
            # клетки и вернулся): корректный финиш без лишнего действия
            if legacy:
                st["finished"] = "goal"
                return build_result(nid, False)
            record_goal(nid, world, required, actions)

        gen = successors(level, state, world, required)
        st["transitions"] += len(gen)
        for ns, nw, nreq, label, cells, cost in gen:
            nw2 = collect_items(level, nw, cells)
            c_actions = actions + cost
            if exit_opened(level, nw2) and (cells & level.exit_bit):
                if legacy:
                    nodes.append((("GOAL", 0, 0), nw2, nreq, label, nid))
                    st["finished"] = "goal"
                    return build_result(len(nodes) - 1, False)
                if greedy:
                    c = (sum(nreq), c_actions)
                    if best_goal is None or c < best_goal:
                        best_goal = c
                        nodes.append((("GOAL", 0, 0), nw2, nreq, label, nid))
                        heapq.heappush(pq, (0, 0, c_actions, len(nodes) - 1))
                else:
                    cand = (sum(nreq), -collected_items(level, nw2), c_actions)
                    if best_goal is None or cand < best_goal:
                        best_goal = cand
                        best_goal_nid = len(nodes)
                        nodes.append((("GOAL", 0, 0), nw2, nreq, label, nid))
                continue
            if ns[0] == "DEAD":
                continue
            if not greedy and best_goal is not None and sum(nreq) > best_goal[0]:
                continue  # хуже по первому критерию; лучшей целью уже не станет
            add_label((ns, nw2), nreq, c_actions, (ns, nw2, nreq, label, nid))
            if len(nodes) > node_cap:
                limit_hit = True
                pq = []
                break

    if best_goal is None:
        if limit_hit:
            st["finished"] = "node_cap"
            if allow_fallback and not greedy:
                gp = _phase_greedy(level) or greedy_plan(level)
                if gp is not None:
                    gpath, greq, gused, _gcount, gcoll = gp
                    return {"status": "solvable",
                            "reason": ("plan found by greedy fallback; minimality "
                                       "not proven (exact search hit the node cap)"),
                            "actions": gpath, "required": greq, "used": gused,
                            "collected": gcoll, "items": level.consumable_count,
                            "nodes": len(nodes), "optimal": False, "stats": st}
                # последняя надежда: неоптимальный план лучше, чем вообще без
                # прохождения; старая цель (меньше предметов на старте, затем
                # действия) находит *какой-то* план дёшево, без раздувания на
                # критерии максимума сбора
                res2 = solve(level, node_cap=max(node_cap * 4, 1000000), stats=None,
                             legacy=True, allow_fallback=False)
                if res2.get("status") == "solvable":
                    res2["reason"] = ("plan found by last-resort search; minimality "
                                      "not proven (node cap)")
                    res2["optimal"] = False
                    res2["stats"] = st
                    return res2
            return {"status": "limit", "reason": "search node limit reached (result unknown)",
                    "actions": [], "required": (0, 0, 0), "used": (0, 0, 0),
                    "collected": 0, "items": level.consumable_count,
                    "nodes": len(nodes), "optimal": False, "stats": st}
        st["finished"] = "exhausted"
        return {"status": "impossible", "reason": "no plan reaches the exit",
                "actions": [], "required": (0, 0, 0), "used": (0, 0, 0),
                "collected": 0, "items": level.consumable_count,
                "nodes": len(nodes), "optimal": True, "stats": st}

    nid = goal_id if greedy else best_goal_nid
    st["finished"] = "goal"
    return build_result(nid, not limit_hit)


def main():
    ap = argparse.ArgumentParser(description="Решает уровни Bumpy по метаданным.")
    ap.add_argument("levels", nargs="?", default=DEFAULT_LEVELS,
                    help="путь к levels.json (по умолчанию main/levels.json)")
    ap.add_argument("--level", type=int, help="решить один уровень (нумерация с 1)")
    ap.add_argument("--all", action="store_true", help="решить все уровни")
    ap.add_argument("--summary", action="store_true", help="одна строка на уровень")
    ap.add_argument("--json", action="store_true", help="вывести JSON")
    ap.add_argument("--node-cap", type=int, default=300000,
                    help="максимум узлов поиска на уровень (по умолчанию 300000)")
    ap.add_argument("--stats", action="store_true",
                    help="печатать статистику поиска по уровням")
    args = ap.parse_args()

    with open(args.levels) as fh:
        model = json.load(fh)

    levels = model["levels"]
    if args.level:
        sel = [levels[args.level - 1]]
    elif args.all:
        sel = levels
    else:
        sel = [levels[0]]

    results = []
    for data in sel:
        level = Level(data)
        st = {} if args.stats else None
        res = solve(level, node_cap=args.node_cap, stats=st)
        res.update(level=level.index, collectibles=level.collectibles,
                   timer=level.timer, exit_cell=(level.exit_r, level.exit_c))
        results.append(res)

    if args.json:
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    for res in results:
        req = res["required"]
        used = res.get("used", (0, 0, 0))
        req_txt = ", ".join(f"{n} {k}" for n, k in zip(req, RESOURCES) if n) or "none"
        used_txt = ", ".join(f"{n} {k}" for n, k in zip(used, RESOURCES) if n) or "none"
        if args.summary or args.all:
            extra = f"  ({res['reason']})" if res["reason"] else ""
            coll = res.get("collected", 0)
            tot = res.get("items", 0)
            print(f"L{res['level']:>3} {res['status']:<10} "
                  f"actions={len(res['actions']):<3} collected={coll}/{tot} "
                  f"start=[{req_txt}] used=[{used_txt}]{extra}")
        else:
            print(f"Level {res['level']}: {res['status']}")
            if res["reason"]:
                print(f"  reason: {res['reason']}")
            print(f"  start items needed: {req_txt}")
            print(f"  items used: {used_txt}")
            print(f"  actions ({len(res['actions'])}):")
            for i, a in enumerate(res["actions"], 1):
                print(f"    {i:>3}. {a}")
        if args.stats and res.get("stats"):
            print("  stats:", json.dumps(res["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
