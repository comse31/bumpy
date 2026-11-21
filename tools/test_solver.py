#!/usr/bin/env python3
"""Regression tests for tools/solve_level.py.

Run with:  python3 tools/test_solver.py
(with plain asserts, no external test framework required)
"""

import importlib.util
import heapq
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sv", os.path.join(HERE, "solve_level.py"))
sv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sv)


def mk(lo, hi, objs, start, tcell, timer=0):
    return {"level": 1, "theme": 1, "timer": timer, "start_cell": start,
            "timer_cell": tcell,
            "grid_lo": lo, "grid_hi": hi, "objects": objs}


def blank():
    return [[0] * 6 for _ in range(6)]


def meta_cell(r, c):
    return r * 6 + c  # r is a metadata row (0 = top)


def brute(level, cap=2000000):
    """Exhaustive reference for the lexicographic objective
    (sum required, -collected consumables, actions)."""
    start_state = (level.start_r, level.start_c, "plat")
    world = sv.collect_items(level, level.initial_world(),
                             sv.rc_bit(level.start_r, level.start_c))
    req0 = (0, 0, 0)
    st0 = sv.start_state_of(level, world, req0)
    if st0 is None:
        return {"status": "impossible", "required": (0, 0, 0),
                "actions": [], "collected": 0}
    start_state, world, req0 = st0
    nodes = [(start_state, world, req0, None, None)]
    labels = {(start_state, world): [(req0, 0)]}
    pq = [(sum(req0), 0, 0)]
    best = None  # (sum required, -collected, actions, node id)

    def offer(world, req, acts, nid):
        nonlocal best
        cand = (sum(req), -sv.collected_items(level, world), acts, nid)
        if best is None or cand[:3] < best[:3]:
            best = cand

    def add(key, req, acts, node):
        lst = labels.get(key)
        if lst is not None:
            for r0, a0 in lst:
                if (r0[0] <= req[0] and r0[1] <= req[1] and r0[2] <= req[2]
                        and a0 <= acts):
                    return
            lst = [x for x in lst
                   if not (req[0] <= x[0][0] and req[1] <= x[0][1]
                           and req[2] <= x[0][2] and acts <= x[1])]
        else:
            lst = []
        labels[key] = lst
        lst.append((req, acts))
        nodes.append(node)
        heapq.heappush(pq, (sum(req), acts, len(nodes) - 1))

    while pq:
        _s, acts, nid = heapq.heappop(pq)
        if best is not None and _s > best[0]:
            break
        state, world, req, _l, _p = nodes[nid]
        if state[0] == "GOAL" or (sv.exit_opened(level, world)
                                  and (state[0], state[1]) == level.exit):
            offer(world, req, acts, nid)
        for ns, nw, nreq, label, cells, cost in sv.successors(level, state, world, req):
            nw2 = sv.collect_items(level, nw, cells)
            nacts = acts + cost
            if sv.exit_opened(level, nw2) and (cells & level.exit_bit):
                gnid = len(nodes)
                nodes.append((("GOAL", 0, 0), nw2, nreq, label, nid))
                offer(nw2, nreq, nacts, gnid)
                continue
            if ns[0] == "DEAD":
                continue
            if best is not None and sum(nreq) > best[0]:
                continue
            add((ns, nw2), nreq, nacts, (ns, nw2, nreq, label, nid))
            if len(nodes) > cap:
                return {"status": "limit", "required": (0, 0, 0),
                        "actions": [], "collected": 0}
    if best is None:
        return {"status": "impossible", "required": (0, 0, 0),
                "actions": [], "collected": 0}
    nid = best[3]
    count = 0
    n = nid
    while nodes[n][4] is not None:
        count += 1
        n = nodes[n][4]
    return {"status": "solvable", "required": nodes[nid][2],
            "actions": [None] * count, "collected": -best[1]}


def exact(level):
    return sv.solve(level, node_cap=300000)


def check_cross(level, name):
    a, b = exact(level), brute(level)
    assert a["status"] == b["status"], (name, "status", a["status"], b["status"])
    if a["status"] == "solvable":
        assert sum(a["required"]) == sum(b["required"]), (name, "req", a["required"], b["required"])
        assert a["required"] == b["required"], (name, "vec", a["required"], b["required"])
        assert len(a["actions"]) == len(b["actions"]), (name, "actions", len(a["actions"]), len(b["actions"]))
        assert a.get("collected") == b.get("collected"), (name, "collected", a.get("collected"), b.get("collected"))
    print(f"ok  cross {name}: {a['status']} req={a['required']} "
          f"act={len(a['actions'])} coll={a.get('collected')}")


def test_basic_hop_collect_exit():
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]     # bottom row platforms (meta row 5)
    objs = blank()
    objs[5] = [0, 0, 5, 0, 0, 0]   # one collectible at col 2
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    check_cross(lvl, "hop-collect-exit")


def test_wall_needs_key_on_level():
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]
    hi = blank()
    hi[5][1] = 1                   # destructible wall between col1 and col2
    objs = blank()
    objs[5][1] = 2                 # a key on the level
    objs[5][5] = 5                 # collectible past the wall
    lvl = sv.Level(mk(lo, hi, objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    check_cross(lvl, "wall-key-on-level")


def test_block_needs_hammer_on_level():
    lo = blank()
    lo[5] = [1, 1, 10, 1, 1, 1]    # brick block at col 2
    objs = blank()
    objs[5][1] = 1                 # hammer before the block
    objs[5][5] = 5
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    check_cross(lvl, "block-hammer-on-level")


def test_equal_sum_vectors_not_collapsed():
    # Two symmetric ways through: either spend a key (wall) or a hammer (block),
    # with nothing on the level, so the answer needs exactly one carried item.
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]
    lo[4] = [1, 10, 1, 1, 1, 1]    # block up top at col 1
    hi = blank()
    hi[5][1] = 1                   # wall on the bottom at the same boundary
    objs = blank()
    objs[5][5] = 5
    lvl = sv.Level(mk(lo, hi, objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    r = exact(lvl)
    assert r["status"] == "solvable", r
    assert sum(r["required"]) == 1, r["required"]
    print(f"ok  equal-sum: req={r['required']}")


def test_bad_metadata_impossible():
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]
    objs = blank()                 # timer 1 but no collectible
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    r = exact(lvl)
    assert r["status"] == "impossible", r
    print("ok  bad-metadata -> impossible")


def test_block_break_single_action_stable():
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]     # bottom (screen row 0) - stable rest
    lo[4][0] = 10                  # brick block at screen row 1, col 0
    objs = blank()
    objs[5][5] = 5
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    gen = sv.successors(lvl, (0, 0, "plat"), lvl.initial_world(), (0, 0, 0))
    breaks = [g for g in gen if "break block" in g[3]]
    assert breaks, [g[3] for g in gen]
    assert all(g[5] == 1 for g in breaks), breaks            # one action
    assert all(g[2][2] == 1 for g in breaks), breaks         # one hammer
    assert all(sv.block_destroyed(lvl, 1, 0, g[1]) for g in breaks), breaks
    print("ok  block-break-one-action-stable")


def test_block_break_per_row_on_shrink():
    lo = blank()
    lo[5][0] = 1                   # solid under the ball (screen row 0)
    lo[4][0] = 2                   # shrinkable platform (screen row 1)
    lo[3][0] = 10                  # brick block above it (screen row 2)
    objs = blank()
    objs[5][5] = 5
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    gen = sv.successors(lvl, (1, 0, "plat"), lvl.initial_world(), (0, 0, 0))
    hits = [g for g in gen if "from below" in g[3]]
    assert hits, [g[3] for g in gen]
    # above shrink the break is NOT collapsed: one row per action, one hammer on
    # the first strike, the block not yet destroyed
    assert all(g[5] == 1 for g in hits), hits
    assert all(sv.block_broken(lvl, 2, 0, g[1]) == 1 for g in hits), hits
    assert all(not sv.block_destroyed(lvl, 2, 0, g[1]) for g in hits), hits
    assert all(g[2][2] == 1 for g in hits), hits
    print("ok  block-break-per-row-on-shrink")


def test_wall_break_one_action_stable():
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]     # stable floor at screen row 0
    hi = blank()
    hi[5][0] = 3                   # durability-3 partition at boundary 1, row 0
    objs = blank()
    objs[5][5] = 5
    lvl = sv.Level(mk(lo, hi, objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    gen = sv.successors(lvl, (0, 0, "plat"), lvl.initial_world(), (0, 0, 0))
    br = [g for g in gen if "break wall" in g[3]]
    assert br, [g[3] for g in gen]
    # from a stable platform a partition is broken in one action
    assert all(g[5] == 1 for g in br), br
    assert all(g[2][1] == 3 for g in br), br
    print("ok  wall-break-one-action-stable")


def test_wall_break_per_hit_on_shrink():
    lo = blank()
    lo[5][0] = 2                   # shrinkable rest (3 uses) at screen row 0
    lo[5][1] = 1
    hi = blank()
    hi[5][0] = 3                   # durability-3 partition at boundary 1, row 0
    objs = blank()
    objs[5][5] = 5
    lvl = sv.Level(mk(lo, hi, objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    gen = sv.successors(lvl, (0, 0, "plat"), lvl.initial_world(), (0, 0, 0))
    br = [g for g in gen if "break wall" in g[3]]
    assert br, [g[3] for g in gen]
    # from a shrinkable platform the break is NOT collapsed: one action per hit
    assert all(g[5] == 3 for g in br), br
    assert all(g[2][1] == 3 for g in br), br
    print("ok  wall-break-per-hit-on-shrink")


def test_prefers_more_collected_same_start_items():
    # Two routes to the exit need no items at start. The short one runs straight
    # along the floor (5 actions, collects nothing); the long one detours onto a
    # platform to grab a drop (6 actions, collects one). The objective values
    # collected before actions, so the detour must win.
    lo = blank()
    lo[5] = [1, 1, 1, 1, 1, 1]     # screen row 0: solid floor
    lo[4][3] = 1                   # screen row 1, col 3: a platform
    objs = blank()
    objs[4][3] = 3                 # a drop resting on it
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=0))
    r = exact(lvl)
    assert r["status"] == "solvable", r
    assert r["required"] == (0, 0, 0), r["required"]
    assert r["collected"] == 1, r
    check_cross(lvl, "prefers-more-collected")


def test_sticky_start_is_a_normal_rest():
    lo = blank()
    lo[5] = [5, 1, 1, 1, 1, 1]     # bottom row; the start cell is sticky
    objs = blank()
    objs[5][2] = 5                 # collectible at (0,2)
    lvl = sv.Level(mk(lo, blank(), objs, meta_cell(5, 0), meta_cell(5, 5), timer=1))
    check_cross(lvl, "sticky-start")


def main():
    test_basic_hop_collect_exit()
    test_wall_needs_key_on_level()
    test_block_needs_hammer_on_level()
    test_equal_sum_vectors_not_collapsed()
    test_bad_metadata_impossible()
    test_block_break_single_action_stable()
    test_block_break_per_row_on_shrink()
    test_wall_break_one_action_stable()
    test_wall_break_per_hit_on_shrink()
    test_prefers_more_collected_same_start_items()
    test_sticky_start_is_a_normal_rest()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
