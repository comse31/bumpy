#!/usr/bin/env python3
"""Solver / walkthrough planner for Bumpy levels.

Given the level metadata in main/levels.json, this tool builds a discrete model
of the ball's movement and of the gameplay-element rules (mirroring
main/ball/ball.script, main/platforms/*, main/walls/*) and searches for the
minimum sequence of player actions that completes the level, together with the
minimum list of items (drops / keys / hammers) the player must already carry at
level start and the items the plan actually spends.

Coordinates are screen coordinates: row 0 is the bottom row, col 0 the left
column. levels.json stores metadata rows top-to-bottom, so row_meta is
converted to row_screen = 5 - row_meta.

Model (a deliberate abstraction of the real continuous physics):

* Rest state: the ball is bouncing in place on a solid surface -- a platform
  cell (row, col), or the top of a brick block (a block at (row-1, col)).
* Lateral hop (left/right): move one column at the current row. Blocked by a
  vertical partition (a destructible one costs its remaining durability in
  keys) or by a brick block; otherwise the ball lands on the first surface at
  or below that row.
* High jump: rises to the first obstacle above in its column. While rising, at
  any crossed row the player may divert one column sideways (same blocking
  rules), landing on the first surface at or below that row. A high jump cannot
  divert at the row of the obstacle itself (the ball stops just below it), so
  climbing needs open space above. A plain high jump returns to the same cell
  but still collects items it rises through.
* Sloped platform: a landing is redirected one cell to the slope side (with no
  player control); a slope pointing off the field acts as a normal platform.
* Sticky platform: the ball rests and may high-jump or hop. The top of a brick
  block behaves as solid but forbids the high jump.
* Shrinkable platform: it is consumed by the action the ball performs from it,
  not by the landing, so a one-use platform is a single launch pad -- the ball
  jumps off and the platform then vanishes (any later landing there falls
  through). This is what lets a ball stranded on a dying platform drop away.
* Dangerous surfaces: spikes are lethal; burning platforms consume one drop
  (else lethal).
* A brick block is broken from below by repeated high jumps: the first hit
  consumes one hammer, and `rows` (8) hits destroy it. Partial hits do not
  change the block's collision, so it is modelled as a single collapsed action.
* Collectibles (object code >= 5) open the exit once `timer` of them are taken.
  When the exit opens, the game deletes the platform in the exit cell, so that
  cell becomes empty; the level is complete as soon as the ball touches the
  exit sign, which also counts for a move that would otherwise be fatal.

Search: label-setting (lexicographic Dijkstra) over (ball state, world) with a
Pareto front of non-dominated (required, actions) labels, so states are never
pruned merely because two resource vectors have the same sum. Objective is
lexicographic: total items carried in first, then number of player actions. The
queue keeps a priority of (total items, actions + h) where h is the max of two
admissible lower bounds: a column-interval walk and an optimistic all-pairs
distance that ignores hazards. When the exact search hits the node cap, a greedy
fallback (shortest path to the next collectible, with a DFS over the collectible
order) finds a plan that is reported with optimal=False.

State representation: the mutable world is packed into small integers (wall
durability and shrink uses as 2-bit fields, destroyed blocks and the burnt /
collected cell sets as bitmasks), and traversed cells are tracked as a 36-bit
mask, which keeps hashing and world updates cheap.

Usage:
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

# lo layer codes -> platform kind (see main/level/level.script).
SHRINK = {2: 3, 3: 2, 4: 1}          # code -> remaining uses
SLOPE = {6: -1, 7: 1}                # code -> slope direction (bounce side)
BURNING = {8: "solid", 9: "sticky"}  # code -> surface after a drop extinguishes it
BLOCK = 10
SPIKE = 12

# hi layer codes -> remaining durability (main/level/level.script WALL_DURABILITY)
WALL_DURA = {1: 1, 2: 2, 3: 3}

# object codes -> consumable kind (main/level/level.script goodie_factory)
OBJ_KIND = {1: "hammer", 2: "key", 3: "drop", 4: "life"}

RESOURCES = ("drop", "key", "hammer")
RES_INDEX = {name: i for i, name in enumerate(RESOURCES)}


def meta_cell_to_rc(cell):
    """metadata cell index (row 0 = top) -> (screen_row, col)."""
    return (ROWS - 1) - (cell // COLS), cell % COLS


def rc_bit(r, c):
    return 1 << (r * COLS + c)


def pack2(values):
    x = 0
    for i, v in enumerate(values):
        x |= (v & 3) << (2 * i)
    return x


# Mutable part of the level state. Every field is a small immutable int so a
# World can key a dict cheaply.
World = namedtuple("World", "walls shrink blocks burnt collected")


class Level:
    """A single level parsed from levels.json into screen-oriented grids.

    Also precomputes everything static the search needs: packed indices for
    mutable objects, item bitmasks and column-span masks.
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

        self.plat = [[0] * COLS for _ in range(ROWS)]  # screen rows, row 0 = bottom
        self.obj = [[0] * COLS for _ in range(ROWS)]
        for mr in range(ROWS):
            r = (ROWS - 1) - mr
            for c in range(COLS):
                self.plat[r][c] = lo[mr][c]
                self.obj[r][c] = obj[mr][c]

        # partitions: grid column gc is boundary b = gc + 1; borders implicit.
        self.walls = {}
        for mr in range(ROWS):
            r = (ROWS - 1) - mr
            for gc in range(COLS - 1):
                code = hi[mr][gc]
                if code:
                    self.walls[(r, gc + 1)] = code

        # packed indices for mutable objects
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

        # item bitmasks
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

        # column-span masks: col_range[c][lo][hi] = bits of rows lo..hi in column c
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
        """All-pairs optimistic action distances between cells.

        The optimistic graph removes every hazard (walls, blocks, spikes,
        shrink, burning, exit removal) and treats any platform as a safe floor,
        so its distance lower-bounds the real effort and is admissible as a
        heuristic. Distances are in actions between cell indices r*6+c.
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
        return World(self.wall_base, self.shrink_base, 0, 0, 0)

    # -- static queries ----------------------------------------------------

    def wall_code(self, r, b):
        return self.walls.get((r, b), 0)

    def has_block(self, r, c):
        return 0 <= r < ROWS and self.plat[r][c] == BLOCK


# -- packed world helpers --------------------------------------------------

def wall_remaining(level, r, b, world):
    """Remaining durability: -1 if no destructible partition, else 0..3."""
    idx = level.wall_index.get((r, b))
    if idx is None:
        return -1
    return (world.walls >> (2 * idx)) & 3


def wall_set(level, world, r, b, value):
    idx = level.wall_index.get((r, b))
    if idx is None:
        return world
    shift = 2 * idx
    mask = 3 << shift
    return world._replace(walls=(world.walls & ~mask) | ((value & 3) << shift))


def wall_hit(level, world, r, b):
    return wall_set(level, world, r, b, max(0, wall_remaining(level, r, b, world) - 1))


def wall_destroy(level, world, r, b):
    return wall_set(level, world, r, b, 0)


def block_destroyed(level, r, c, world):
    idx = level.block_index.get((r, c))
    return idx is not None and (world.blocks >> idx) & 1 == 1


def block_broken(level, r, c, world):
    return BLOCK_ROWS if block_destroyed(level, r, c, world) else 0


def block_destroy(level, world, r, c):
    idx = level.block_index.get((r, c))
    if idx is None:
        return world
    return world._replace(blocks=world.blocks | (1 << idx))


def shrink_remaining(level, r, c, world):
    idx = level.shrink_index[(r, c)]
    return (world.shrink >> (2 * idx)) & 3


def shrink_dec(level, world, r, c):
    idx = level.shrink_index.get((r, c))
    if idx is None:
        return world
    shift = 2 * idx
    value = max(0, ((world.shrink >> shift) & 3) - 1)
    mask = 3 << shift
    return world._replace(shrink=(world.shrink & ~mask) | (value << shift))


def extinguish(level, world, r, c):
    return world._replace(burnt=world.burnt | rc_bit(r, c))


def collected_collectibles(level, world):
    return (world.collected & level.collectible_mask).bit_count()


def exit_opened(level, world):
    return (level.timer <= 0
            or (world.collected & level.collectible_mask).bit_count() >= level.timer)


def collect_items(level, world, cells):
    """Add the item-bearing cells among the traversed `cells` mask."""
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
    """Available counts per resource = collected - consumed + borrowed."""
    drops = (world.collected & level.drop_mask).bit_count() - world.burnt.bit_count() + required[0]
    keys = (world.collected & level.key_mask).bit_count() - keys_used(level, world) + required[1]
    hammers = (world.collected & level.hammer_mask).bit_count() - world.blocks.bit_count() + required[2]
    return (drops, keys, hammers)


def spend(level, world, required, resource, n=1):
    """Consume `n` of `resource`, borrowing (raising `required`) if needed."""
    have = inventory(level, world, required)[RES_INDEX[resource]]
    if have >= n:
        return required
    req = list(required)
    req[RES_INDEX[resource]] += n - have
    return tuple(req)


def consumed_items(level, world):
    """Items the plan has actually spent, as (drops, keys, hammers)."""
    return (world.burnt.bit_count(), keys_used(level, world), world.blocks.bit_count())


# -- movement model --------------------------------------------------------

def floor_at(level, r, c, world):
    """Surface seen when the ball descends onto (r, c), or None if empty.

    Returns one of: ('solid',), ('sticky',), ('slope', dir), ('spike',),
    ('burn', surface_after), ('shrink',), ('blocktop',).
    """
    if r < 0 or r >= ROWS:
        return None
    # the platform in the exit cell is removed when the exit opens, so the cell
    # becomes empty and the ball falls through it (touching the sign wins)
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
        return None  # the block occupies this cell; its top is at r+1
    if r >= 1 and level.has_block(r - 1, c) and not block_destroyed(level, r - 1, c, world):
        return ("blocktop",)
    return None


def landing(level, c, start_row, world, required, depth=0):
    """Ball descends in column c from `start_row`.

    Returns (outcome, cells_mask): `outcome` is (r, c, kind, world, required)
    with kind in {'plat','blocktop'}, or None if the ball dies (spikes / falls
    off); `cells_mask` marks every cell passed through, which matters because
    touching the exit sign wins even on a fatal move.
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
    """Ball hops from (r, c) one column in direction d and lands.

    A blocked partition costs its durability in keys (destructible) and bounces
    the ball back; a block bounces it back. Returns (outcome, cells_mask).
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
    """Lowest obstacle above (r, c): returns (row, kind) or (None, None)."""
    for rr in range(r + 1, ROWS):
        if level.has_block(rr, c) and not block_destroyed(level, rr, c, world):
            return rr, "block"
        code = level.plat[rr][c]
        if code and code != BLOCK:
            if code in SHRINK and shrink_remaining(level, rr, c, world) <= 0:
                continue
            if (rr, c) == level.exit and exit_opened(level, world):
                continue  # exit cell platform removed
            return rr, "platform"
    return None, None


def successors(level, state, world, required):
    """Return a list of (new_state, new_world, new_required, label, cells, cost).

    `cells` is a 36-bit mask of every cell the ball occupies or passes through
    during the action. `cost` is the number of player actions the move costs.

    A rest on a shrinkable platform is the bounce the player acts on: the
    action consumes one use of the platform, so a one-use platform vanishes
    right after the first jump (any action that stays in the cell then falls).
    """
    r, c, kind = state
    out = []
    rest_shrink = kind != "blocktop" and level.plat[r][c] in SHRINK
    rest_bit = rc_bit(r, c)

    # ---- high jump --------------------------------------------------------
    if kind != "blocktop":
        obs_r, obs_kind = obstacle_above(level, r, c, world)
        rr_max = (obs_r - 1) if obs_r is not None else ROWS - 1
        reach = list(range(r + 1, rr_max + 1))
        hi_cells = rest_bit | (level.col_range[c][r + 1][rr_max] if reach else 0)

        # a high jump is always possible: with nothing above it rises and comes
        # back to the same cell, collecting the items it passes through
        out.append(((r, c, kind), world, required,
                    f"high jump in place at ({r},{c})", hi_cells, 1))

        # break a brick block directly above: repeated hits from below, the
        # first consuming one hammer. Partial hits do not change collision.
        if obs_kind == "block":
            req2, hammered = required, ""
            broken = block_broken(level, obs_r, c, world)
            if broken == 0:
                req2 = spend(level, world, required, "hammer")
                hammered = " (uses 1 hammer)"
            w2 = block_destroy(level, world, obs_r, c)
            out.append(((r, c, kind), w2, req2,
                        f"break block ({obs_r},{c}) from below{hammered}",
                        rest_bit | level.col_range[c][r + 1][obs_r - 1],
                        BLOCK_ROWS - broken))

        # divert one column at each reachable row
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
                    out.append(((r, c, kind), wall_destroy(level, world, rr, b), req2,
                                f"high jump, break wall {b} at row {rr} ({rem} keys)",
                                rise, rem))
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

    # ---- lateral hop ------------------------------------------------------
    for d in (-1, 1):
        c2 = c + d
        if not (0 <= c2 < COLS):
            continue
        b = max(c, c2)
        rem = wall_remaining(level, r, b, world)
        if rem > 0:  # destructible partition: break it fully, bounce back
            req2 = spend(level, world, required, "key", rem)
            out.append(((r, c, kind), wall_destroy(level, world, r, b), req2,
                        f"break wall {b} at row {r} ({rem} keys)", rest_bit, rem))
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
            # a same-cell result may still collect items it passes through (for
            # example a slope bouncing the ball back through a corner cell) or
            # spend a resource; a true no-op is pruned later by label dominance.
            out.append(((r, c, kind), w2, req2,
                        f"hop from ({r},{c}) and return via column {c2}", cells, 1))
        else:
            out.append(((r2, c2r, k2), w2, req2,
                        f"hop ({r},{c}) -> ({r2},{c2r})", cells, 1))

    # consume one use of a shrinkable rest platform per action; if that empties
    # it and the action did not leave the cell, the ball now falls through
    if rest_shrink:
        consumed = []
        for ns, nw, nreq, label, cells, cost in out:
            nw2 = shrink_dec(level, nw, r, c)
            if ns[0] != "DEAD" and ns[0] != "GOAL" and (ns[0], ns[1]) == (r, c) \
                    and shrink_remaining(level, r, c, nw2) <= 0:
                fell, fcells = landing(level, c, r - 1, nw2, nreq)
                if fell is None:
                    # the ball falls off / onto spikes after the platform goes;
                    # keep the transition as fatal so an exit touch along the
                    # way is still detected
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

    # a rest left on a vanished shrinkable platform cannot stay in place
    if kind != "blocktop" and floor_at(level, r, c, world) is None:
        out = [s for s in out if s[0][0] == "DEAD" or s[0][0] == "GOAL"
               or (s[0][0], s[0][1]) != (r, c)]

    return out


def nw_or(nw):
    return nw


# -- search ----------------------------------------------------------------

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
    """Dijkstra (by actions) to the first move satisfying `edge_goal`.

    `edge_goal(cells, world)` decides the phase target. Resources are ignored
    (borrowing is free), and states are deduplicated by (state, world) keeping
    the cheapest, which is enough to find a short path. Returns
    (state, world, required, labels) or None.
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
    """Greedy fallback: repeatedly take a shortest path to any remaining
    collectible, then to the exit. Fast; returns (actions, required, used,
    nodes) or None."""
    start_state = (level.start_r, level.start_c, "plat")
    world = collect_items(level, level.initial_world(),
                          rc_bit(level.start_r, level.start_c))
    req = (0, 0, 0)
    if floor_at(level, level.start_r, level.start_c, world) is None:
        fell, _c = landing(level, level.start_c, level.start_r - 1, world, req)
        if fell is None:
            return None
        start_state = (fell[0], fell[1], fell[2])
        world, req = fell[3], fell[4]

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
    return path, req, consumed_items(level, world), len(path)


def greedy_plan(level, phase_cap=400000, max_depth=24, max_phases=4000):
    """Find a plan by chaining short searches to collectibles and the exit.

    A depth-first search over the order in which collectibles are taken; each
    edge is a shortest path to one collectible / the exit found by
    `_reach_phase`. Fast but not proven minimal: used as a fallback when the
    exact search hits the node cap. Returns (actions, required, used, nodes) or
    None.
    """
    start_state = (level.start_r, level.start_c, "plat")
    world = collect_items(level, level.initial_world(),
                          rc_bit(level.start_r, level.start_c))
    req = (0, 0, 0)
    if floor_at(level, level.start_r, level.start_c, world) is None:
        fell, _c = landing(level, level.start_c, level.start_r - 1, world, req)
        if fell is None:
            return None
        start_state = (fell[0], fell[1], fell[2])
        world, req = fell[3], fell[4]

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
    return labels, freq, consumed_items(level, fworld), len(labels)


def solve(level, node_cap=400000, stats=None, greedy=False, allow_fallback=True):
    """Search for a minimal plan (see module docstring).

    Returns a dict with: status in {'solvable','impossible','limit'}, reason,
    actions (ordered labels), required (start-of-level items), used (items
    actually spent), nodes, optimal (True when minimality was proven) and (if
    `stats` dict is given) search counters.

    When the exact lexicographic-Dijkstra search hits `node_cap`, a greedy
    best-first fallback (`allow_fallback`) is run that finds *a* plan without
    proving minimality, so every passable level still yields a walkthrough; the
    result then carries optimal=False.
    """
    st = stats if stats is not None else {}
    st.update(popped=0, transitions=0, unique_keys=0, labels=0,
              dominance_hits=0, peak_queue=0, peak_labels=0, finished="")

    if level.timer > level.collectibles:
        st["finished"] = "bad_metadata"
        return {"status": "impossible",
                "reason": "fewer collectibles on the level than the exit needs",
                "actions": [], "required": (0, 0, 0), "used": (0, 0, 0),
                "nodes": 0, "stats": st}

    start_state = (level.start_r, level.start_c, "plat")
    start_world = collect_items(level, level.initial_world(),
                                rc_bit(level.start_r, level.start_c))
    req0 = (0, 0, 0)
    # if the start cell has no surface the ball simply falls on spawn
    if floor_at(level, level.start_r, level.start_c, start_world) is None:
        fell, _fcells = landing(level, level.start_c, level.start_r - 1,
                                start_world, req0)
        if fell is None:
            st["finished"] = "start_fall"
            return {"status": "impossible", "reason": "ball falls off at start",
                    "actions": [], "required": req0, "used": (0, 0, 0),
                    "nodes": 0, "stats": st}
        start_state = (fell[0], fell[1], fell[2])
        start_world, req0 = fell[3], fell[4]

    def heuristic(state, world):
        # Admissible lower bound on remaining actions from the optimistic
        # all-pairs distance matrix (walls/blocks/spikes/shrink ignored). The
        # ball must reach the exit and every remaining collectible; for any such
        # target t the path current -> t -> exit costs at least
        # d(cur,t)+d(t,exit), and the whole path costs at least d(cur,exit).
        if state[0] == "GOAL":
            return 0
        D = level.opt_dist
        big = level.opt_big
        cur = state[0] * COLS + state[1]
        e = level.exit_r * COLS + level.exit_c
        rem = level.collectible_mask & ~world.collected
        # bound 2: optimistic all-pairs distance; must reach exit and every
        # remaining collectible t, so path >= d(cur,exit) and >= d(cur,t)+d(t,exit)
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
        # bound 1: column-interval walk (one column per action, rows free)
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
        return best if best > colb else colb

    labels = {}   # (state, world) -> list of non-dominated (required, actions)
    nodes = []    # (state, world, required, action_label, parent_id)
    pq = []       # (sum(required), actions + h, actions, node_id)

    def add_label(key, required, actions, node):
        lst = labels.get(key)
        if greedy:
            # reachability fallback: keep only the cheapest label per key
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
        h = heuristic(key[0], key[1])
        if greedy:
            rem = (level.collectible_mask & ~key[1].collected).bit_count()
            heapq.heappush(pq, (h, rem, actions, len(nodes) - 1))
        else:
            heapq.heappush(pq, (sum(required), actions + h, actions, len(nodes) - 1))

    add_label((start_state, start_world), req0, 0,
              (start_state, start_world, req0, None, None))

    goal_id = None
    best_goal = None
    limit_hit = False

    while pq:
        _summ, _f, actions, nid = heapq.heappop(pq)
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

        if state[0] == "GOAL" or (state[0] != "GOAL" and exit_opened(level, world)
                                  and (state[0], state[1]) == level.exit):
            goal_id = nid
            st["finished"] = "goal"
            break

        gen = successors(level, state, world, required)
        st["transitions"] += len(gen)
        for ns, nw, nreq, label, cells, cost in gen:
            nw2 = collect_items(level, nw, cells)
            c_actions = actions + cost
            if exit_opened(level, nw2) and (cells & level.exit_bit):
                c = (sum(nreq), c_actions)
                if best_goal is None or c < best_goal:
                    best_goal = c
                    nodes.append((("GOAL", 0, 0), nw2, nreq, label, nid))
                    if greedy:
                        heapq.heappush(pq, (0, 0, c[1], len(nodes) - 1))
                    else:
                        heapq.heappush(pq, (c[0], c[1], c[1], len(nodes) - 1))
                continue
            if ns[0] == "DEAD":
                continue
            add_label((ns, nw2), nreq, c_actions, (ns, nw2, nreq, label, nid))
            if len(nodes) > node_cap:
                limit_hit = True
                pq = []
                break

    if goal_id is None:
        if limit_hit:
            st["finished"] = "node_cap"
            if allow_fallback and not greedy:
                gp = _phase_greedy(level) or greedy_plan(level)
                if gp is not None:
                    gpath, greq, gused, gnodes = gp
                    return {"status": "solvable",
                            "reason": ("plan found by greedy fallback; minimality "
                                       "not proven (exact search hit the node cap)"),
                            "actions": gpath, "required": greq, "used": gused,
                            "nodes": len(nodes), "optimal": False, "stats": st}
            return {"status": "limit", "reason": "search node limit reached (result unknown)",
                    "actions": [], "required": (0, 0, 0), "used": (0, 0, 0),
                    "nodes": len(nodes), "optimal": False, "stats": st}
        st["finished"] = "exhausted"
        return {"status": "impossible", "reason": "no plan reaches the exit",
                "actions": [], "required": (0, 0, 0), "used": (0, 0, 0),
                "nodes": len(nodes), "optimal": True, "stats": st}

    path = []
    nid = goal_id
    while nid is not None:
        if nodes[nid][3] is not None:
            path.append(nodes[nid][3])
        nid = nodes[nid][4]
    path.reverse()
    st["finished"] = "goal"
    return {"status": "solvable", "reason": "",
            "actions": path, "required": nodes[goal_id][2],
            "used": consumed_items(level, nodes[goal_id][1]),
            "nodes": len(nodes), "optimal": True, "stats": st}


def main():
    ap = argparse.ArgumentParser(description="Solve Bumpy levels from metadata.")
    ap.add_argument("levels", nargs="?", default=DEFAULT_LEVELS,
                    help="path to levels.json (default: main/levels.json)")
    ap.add_argument("--level", type=int, help="solve a single level (1-based)")
    ap.add_argument("--all", action="store_true", help="solve every level")
    ap.add_argument("--summary", action="store_true", help="one line per level")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--node-cap", type=int, default=300000,
                    help="max search nodes per level (default 300000)")
    ap.add_argument("--stats", action="store_true",
                    help="print search statistics per level")
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
            print(f"L{res['level']:>3} {res['status']:<10} "
                  f"actions={len(res['actions']):<3} start=[{req_txt}] "
                  f"used=[{used_txt}]{extra}")
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
