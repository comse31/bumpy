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


def brute(level, cap=400000):
    """Exhaustive reference: keeps every distinct (required, actions) label."""
    start_state = (level.start_r, level.start_c, "plat")
    world = sv.collect_items(level, level.initial_world(),
                             sv.rc_bit(level.start_r, level.start_c))
    req0 = (0, 0, 0)
    if sv.floor_at(level, level.start_r, level.start_c, world) is None:
        fell, _c = sv.landing(level, level.start_c, level.start_r - 1, world, req0)
        if fell is None:
            return {"status": "impossible", "required": (0, 0, 0), "actions": []}
        start_state = (fell[0], fell[1], fell[2])
        world, req0 = fell[3], fell[4]
    nodes = [(start_state, world, req0, None)]
    seen = {(start_state, world): {(req0, 0)}}
    pq = [(sum(req0), 0, 0)]
    goal = None
    while pq:
        _s, acts, nid = heapq.heappop(pq)
        state, world, req, _p = nodes[nid]
        if state[0] == "GOAL" or (sv.exit_opened(level, world)
                                  and (state[0], state[1]) == level.exit):
            goal = nid
            break
        for ns, nw, nreq, label, cells, cost in sv.successors(level, state, world, req):
            nw2 = sv.collect_items(level, nw, cells)
            nacts = acts + cost
            if sv.exit_opened(level, nw2) and (cells & level.exit_bit):
                if goal is None:
                    goal = len(nodes)
                    nodes.append((("GOAL",), nw2, nreq, nid))
                    heapq.heappush(pq, (sum(nreq), nacts, goal))
                continue
            if ns[0] == "DEAD":
                continue
            key = (ns, nw2)
            lab = (nreq, nacts)
            bucket = seen.setdefault(key, set())
            if lab in bucket:
                continue
            bucket.add(lab)
            nodes.append((ns, nw2, nreq, nid))
            heapq.heappush(pq, (sum(nreq), nacts, len(nodes) - 1))
            if len(nodes) > cap:
                return {"status": "limit", "required": (0, 0, 0), "actions": []}
    if goal is None:
        return {"status": "impossible", "required": (0, 0, 0), "actions": []}
    n, acts = nodes[goal], None
    path = []
    while n[3] is not None:
        path.append(n[0])
        n = nodes[n[3]]
    return {"status": "solvable", "required": nodes[goal][2], "actions": path}


def exact(level):
    return sv.solve(level, node_cap=300000)


def check_cross(level, name):
    a, b = exact(level), brute(level)
    assert a["status"] == b["status"], (name, "status", a["status"], b["status"])
    if a["status"] == "solvable":
        assert sum(a["required"]) == sum(b["required"]), (name, "req", a["required"], b["required"])
        assert a["required"] == b["required"], (name, "vec", a["required"], b["required"])
        assert len(a["actions"]) == len(b["actions"]), (name, "actions", len(a["actions"]), len(b["actions"]))
    print(f"ok  cross {name}: {a['status']} req={a['required']} act={len(a['actions'])}")


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


def main():
    test_basic_hop_collect_exit()
    test_wall_needs_key_on_level()
    test_block_needs_hammer_on_level()
    test_equal_sum_vectors_not_collapsed()
    test_bad_metadata_impossible()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
