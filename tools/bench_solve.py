#!/usr/bin/env python3
"""Reproducible benchmark + difficulty rating for tools/solve_level.py.

Runs the solver over some or all levels of main/levels.json, records per-level
metrics (status, optimality, actions, start/used items, nodes, seconds) plus a
difficulty score, and writes:
  * JSON data (default tools/levels_data.json)
  * a self-contained, sortable HTML report (default tools/levels_report.html)

Usage:
    python3 tools/bench_solve.py
    python3 tools/bench_solve.py --node-cap 300000 --out /tmp/bench.json
    python3 tools/bench_solve.py --module /tmp/solve_level_baseline.py --no-html

Difficulty rating
-----------------
A level is *not* hard just because the walkthrough is long (level 1 is trivial
yet ~40 hops). The rating is a 0..100 weighted sum of normalised, mostly
structural factors, so length only contributes a little:

  25 * resource pressure   min(required_items, 8) / 8
  25 * hazard density      min(spikes + burning, 36) / 36
  15 * obstacle density    min(destructible_walls + blocks, 18) / 18
  10 * instability         min(slopes + shrink, 36) / 36
  10 * route complexity    log10(nodes) / log10(node_cap)      (search effort)
  10 * execution length    min(actions, 60) / 60
   5 * collection load     min(collectibles, 16) / 16

Bands: <=15 easy, <=30 medium, <=50 hard, else expert. All raw components are
kept in the JSON so the formula can be re-tuned without re-solving.
"""

import argparse
import importlib.util
import json
import math
import multiprocessing as mp
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODULE = os.path.join(HERE, "solve_level.py")
DEFAULT_LEVELS = os.path.join(HERE, "..", "main", "levels.json")
DEFAULT_OUT = os.path.join(HERE, "levels_data.json")
DEFAULT_HTML = os.path.join(HERE, "levels_report.html")

RESOURCES = ("drops", "keys", "hammers")
STATUS_COLOR = {"solvable": "#1a7f37", "impossible": "#b42318", "limit": "#b54708"}


def load_solver(path):
    spec = importlib.util.spec_from_file_location("solver_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def features(sv, level, res, node_cap, seconds):
    plat = level.plat
    spikes = sum(1 for r in range(6) for c in range(6) if plat[r][c] == sv.SPIKE)
    burning = sum(1 for r in range(6) for c in range(6) if plat[r][c] in sv.BURNING)
    slopes = sum(1 for r in range(6) for c in range(6) if plat[r][c] in sv.SLOPE)
    shrink = len(level.shrink_index)
    walls = len(level.wall_index)
    blocks = len(level.block_index)
    empty = sum(1 for r in range(6) for c in range(6) if plat[r][c] == 0)
    req = res.get("required", (0, 0, 0))
    used = res.get("used", (0, 0, 0))
    collected = res.get("collected", 0)
    items = res.get("items", 0)
    pct = 100.0 if items == 0 else round(100.0 * collected / items, 1)
    return {
        "spikes": spikes, "burning": burning, "slopes": slopes, "shrink": shrink,
        "walls": walls, "blocks": blocks, "empty": empty,
        "collectibles": level.collectibles, "timer": level.timer,
        "required_sum": sum(req), "used_sum": sum(used),
        "collected": collected, "items": items, "collected_pct": pct,
        "actions": len(res.get("actions", [])),
        "nodes": res.get("nodes", 0),
        "optimal": res.get("optimal", True),
        "seconds": seconds,
    }


def difficulty(f, node_cap):
    R = min(f["required_sum"], 8) / 8
    A = min(f["actions"], 60) / 60
    H = min(f["spikes"] + f["burning"], 36) / 36
    O = min(f["walls"] + f["blocks"], 18) / 18
    S = min(f["slopes"] + f["shrink"], 36) / 36
    C = min(f["collectibles"], 16) / 16
    T = min(math.log10(f["nodes"] + 1) / math.log10(node_cap + 1), 1.0)
    score = 25 * R + 25 * H + 15 * O + 10 * S + 10 * T + 10 * A + 5 * C
    return round(score, 1)


def band(score):
    if score <= 15:
        return "easy"
    if score <= 30:
        return "medium"
    if score <= 50:
        return "hard"
    return "expert"


def fmt_vec(v):
    if not v:
        return "0"
    return ", ".join(f"{n} {RESOURCES[i]}" for i, n in enumerate(v) if n) or "0"


def render_html(rows, summary, module, node_cap, levels_path, meta):
    data = json.dumps({"rows": rows, "summary": summary, "meta": meta},
                      ensure_ascii=False).replace("</", "<\\/")
    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Bumpy solver report</title>
<style>
 body { font: 13px/1.4 system-ui, sans-serif; margin: 24px; color: #1f2328; }
 h1 { font-size: 18px; margin-bottom: 4px; }
 .meta { color:#57606a; margin-bottom: 10px; }
 .kpi { display:flex; gap:14px; flex-wrap:wrap; margin: 10px 0 14px; }
 .kpi div { background:#f6f8fa; border-radius:8px; padding:7px 12px; }
 .legend { color:#57606a; font-size:12px; margin-bottom:10px; }
 table { border-collapse: collapse; width: 100%; }
 th, td { border: 1px solid #d0d7de; padding: 4px 8px; text-align: left; vertical-align: top; }
 th { background: #f6f8fa; position: sticky; top: 0; cursor: pointer; user-select: none; }
 th:hover { background:#eaeef2; }
 th .arrow { color:#8c959f; font-size:10px; }
 td.num { text-align: right; font-variant-numeric: tabular-nums; }
 .badge { color:#fff; padding:1px 8px; border-radius:10px; font-size:12px; }
 .fb { color:#b54708; font-size:11px; margin-left:4px; }
 .bar { display:inline-block; height:10px; background:#0969da; border-radius:3px; vertical-align:middle; }
 .plan { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size:12px;
         background:#f6f8fa; padding:6px; border-radius:6px; margin-top:4px; max-height:340px; overflow:auto; }
 details summary { cursor:pointer; color:#0969da; }
 .filters { margin-bottom:8px; }
 .filters button { margin-right:6px; }
</style></head><body>
<h1>Bumpy solver report</h1>
<div class="meta">module: <code id="mod"></code> · levels: <code id="lvl"></code> · node-cap: <span id="cap"></span></div>
<div class="kpi" id="kpi"></div>
<div class="legend">Сложность 0..100 = 25·ресурсы + 25·опасности + 15·препятствия + 10·нестабильность + 10·сложность маршрута (log узлов) + 10·длина + 5·сбор.
Кликните по заголовку столбца для сортировки. Бейдж <span class="fb">fallback</span> — план найден, но минимальность не доказана.</div>
<div class="filters" id="filters"></div>
<table><thead id="head"></thead><tbody id="body"></tbody></table>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
document.getElementById('mod').textContent = DATA.meta.module;
document.getElementById('lvl').textContent = DATA.meta.levels;
document.getElementById('cap').textContent = DATA.meta.node_cap;
const COLORS = __COLORS__;
const statusColor = s => COLORS[s] || '#333';
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const vec = v => (!v || !v.some(x=>x)) ? '0' : v.map((n,i)=>n?`${n} ${['drops','keys','hammers'][i]}`:null).filter(Boolean).join(', ');

const COLS = [
  {key:'level', label:'Уровень', num:true},
  {key:'status', label:'Статус'},
  {key:'difficulty', label:'Сложность', num:true},
  {key:'band', label:'Класс'},
  {key:'actions', label:'Действий', num:true},
  {key:'start_sum', label:'На старте', num:true},
  {key:'used_sum', label:'Использовано', num:true},
  {key:'collected_pct', label:'Собрано %', num:true},
  {key:'collectibles', label:'Собрать', num:true},
  {key:'credits', label:'Опасн/Препят/Нестаб', num:false},
  {key:'nodes', label:'Узлов', num:true},
  {key:'seconds', label:'Время, с', num:true},
  {key:'plan', label:'План', num:false},
];
let sortKey = 'difficulty', sortDir = 1, statusFilter = null;

function applyFilter(rows){
  return statusFilter ? rows.filter(r => r.status === statusFilter) : rows.slice();
}
function sortRows(rows){
  return rows.sort((a,b)=>{
    let x=a[sortKey], y=b[sortKey];
    if (x===undefined || x===null) x = (typeof y==='number'? -1 : '');
    if (y===undefined || y===null) y = (typeof x==='number'? -1 : '');
    if (typeof x === 'number' && typeof y === 'number') return (x-y)*sortDir;
    return String(x).localeCompare(String(y))*sortDir;
  });
}
function rowObj(r){
  const plan = (r.actions_list||[]);
  return {
    level:r.level, status:r.status, difficulty:r.difficulty, band:r.band,
    actions:plan.length, start_sum:r.required_sum, used_sum:r.used_sum,
    collected_pct:r.collected_pct,
    collectibles:r.collectibles, nodes:r.nodes, seconds:r.seconds,
    credits:`${r.spikes+r.burning}/${r.walls+r.blocks}/${r.slopes+r.shrink}`,
    plan:plan,
  };
}
function render(){
  const rows = sortRows(applyFilter(DATA.rows.map(rowObj)));
  document.getElementById('head').innerHTML = '<tr>' + COLS.map(c =>
     `<th data-k="${c.key}">${esc(c.label)} <span class="arrow">${c.key===sortKey?(sortDir>0?'▲':'▼'):''}</span></th>`).join('') + '</tr>';
  document.getElementById('body').innerHTML = rows.map(r => {
    const maxD = 100, w = Math.max(2, Math.round(r.difficulty/maxD*60));
    const planHtml = r.plan.length ? `<details><summary>план (${r.plan.length})</summary><div class="plan">${r.plan.map((a,i)=>`${i+1}. ${esc(a)}`).join('<br>')}</div></details>` : '';
    const fb = (DATA.rows.find(x=>x.level===r.level)||{}).optimal===false ? '<span class="fb">fallback</span>' : '';
    return `<tr>
      <td class="num">${r.level}</td>
      <td><span class="badge" style="background:${statusColor(r.status)}">${esc(r.status)}</span>${fb}</td>
      <td class="num">${r.difficulty} <span class="bar" style="width:${w}px"></span></td>
      <td>${esc(r.band)}</td>
      <td class="num">${r.actions}</td>
      <td class="num">${esc(vec(DATA.rows.find(x=>x.level===r.level).required))} (${r.start_sum})</td>
      <td class="num">${esc(vec(DATA.rows.find(x=>x.level===r.level).used))} (${r.used_sum})</td>
      <td class="num">${r.collected_pct}%</td>
      <td class="num">${r.collectibles}</td>
      <td>${r.credits}</td>
      <td class="num">${r.nodes}</td>
      <td class="num">${r.seconds.toFixed(2)}</td>
      <td>${planHtml}</td>
    </tr>`;
  }).join('');
  document.querySelectorAll('#head th').forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = (k==='level'||k==='difficulty'||k==='status')?1:-1; }
    render();
  });
}
(function initKpi(){
  const s = DATA.summary;
  const counts = s.counts || {};
  const avgColl = DATA.rows.length
    ? DATA.rows.reduce((a,r)=>a+r.collected_pct,0)/DATA.rows.length : 0;
  document.getElementById('kpi').innerHTML =
    Object.keys(counts).sort().map(k=>`<div>${k}: <b>${counts[k]}</b></div>`).join('')
    + `<div>оптимально: <b>${s.optimal_count||0}</b></div>`
    + `<div>фолбэк: <b>${s.fallback_count||0}</b></div>`
    + `<div>ср. собрано: <b>${avgColl.toFixed(1)}%</b></div>`
    + `<div>суммарно: <b>${(s.total_seconds||0).toFixed(1)}s</b></div>`;
  const states = [...new Set(DATA.rows.map(r=>r.status))];
  document.getElementById('filters').innerHTML =
    `<button data-f="">все</button>` + states.map(st=>`<button data-f="${st}">${esc(st)}</button>`).join('');
  document.querySelectorAll('#filters button').forEach(b => b.onclick = () => {
    statusFilter = b.dataset.f || null; render();
  });
})();
render();
</script>
</body></html>
""".replace("__DATA__", data).replace("__COLORS__", json.dumps(STATUS_COLOR))


def run_level(sv, data, node_cap, n):
    """Solve one level and build its report row (no printing)."""
    level = sv.Level(data)
    t0 = time.time()
    res = sv.solve(level, node_cap=node_cap)
    dt = time.time() - t0
    f = features(sv, level, res, node_cap, round(dt, 3))
    d = difficulty(f, node_cap)
    row = {
        "level": n, "status": res.get("status"),
        "difficulty": d, "band": band(d),
        "required": list(res.get("required", (0, 0, 0))),
        "used": list(res.get("used", (0, 0, 0))),
        "actions_list": res.get("actions", []),
        "reason": res.get("reason", ""), "nodes": res.get("nodes", 0),
        "optimal": res.get("optimal", True), "seconds": round(dt, 3),
    }
    row.update(f)
    return row


def print_row(row):
    f = row
    print(f"L{row['level']:>3} {row.get('status','?'):<9} diff={row['difficulty']:5.1f} "
          f"{row['band']:<6} act={f['actions']:<3} {'' if row['optimal'] else 'fb '}"
          f"coll={f['collected']}/{f['items']} ({f['collected_pct']:.0f}%) "
          f"start={fmt_vec(row['required'])} used={fmt_vec(row['used'])} "
          f"nodes={row['nodes']:<7} {row['seconds']:6.2f}s", flush=True)


# --- parallel workers (levels are fully independent, so this is embarrassingly
# --- parallel). The solver module and levels are (re)loaded per process via an
# --- initializer so this works with fork, forkserver and spawn alike.
_W = {}


def _init_worker(module_path, levels_path, node_cap):
    _W["sv"] = load_solver(module_path)
    with open(levels_path) as fh:
        _W["levels"] = json.load(fh)["levels"]
    _W["node_cap"] = node_cap


def _run_one(n):
    return run_level(_W["sv"], _W["levels"][n - 1], _W["node_cap"], n)


def _node_hint(out_path):
    """Previous per-level node counts, used to schedule heavy levels first."""
    try:
        with open(out_path) as fh:
            return {r["level"]: r["nodes"] for r in json.load(fh)["rows"]}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--module", default=DEFAULT_MODULE)
    ap.add_argument("--levels", default=DEFAULT_LEVELS)
    ap.add_argument("--node-cap", type=int, default=300000)
    ap.add_argument("--from", dest="first", type=int, default=1)
    ap.add_argument("--to", dest="last", type=int, default=100)
    ap.add_argument("--out", default=DEFAULT_OUT, help="write JSON metrics here")
    ap.add_argument("--html", default=DEFAULT_HTML, help="write HTML report here")
    ap.add_argument("--no-html", action="store_true", help="skip the HTML report")
    ap.add_argument("--jobs", type=int, default=0,
                    help="parallel worker processes (0 = auto, 1 = sequential)")
    args = ap.parse_args()

    tasks = list(range(args.first, args.last + 1))
    jobs = args.jobs if args.jobs > 0 else min(os.cpu_count() or 1, 16)
    jobs = min(jobs, len(tasks))

    rows = []
    total_t = 0.0
    t_start = time.time()

    if jobs <= 1:
        sv = load_solver(args.module)
        with open(args.levels) as fh:
            levels = json.load(fh)["levels"]
        for n in tasks:
            row = run_level(sv, levels[n - 1], args.node_cap, n)
            total_t += row["seconds"]
            rows.append(row)
            print_row(row)
    else:
        # heavy levels first (by last run's node counts) to shrink the straggler
        hint = _node_hint(args.out)
        order = sorted(tasks, key=lambda n: hint.get(n, 0), reverse=True)
        print(f"parallel: {jobs} workers, {len(tasks)} levels", flush=True)
        ctx = mp.get_context()
        with ctx.Pool(processes=jobs, initializer=_init_worker,
                      initargs=(args.module, args.levels, args.node_cap)) as pool:
            for row in pool.imap_unordered(_run_one, order, chunksize=1):
                total_t += row["seconds"]
                rows.append(row)
                print_row(row)
    rows.sort(key=lambda r: r["level"])

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    slowest = max(rows, key=lambda r: r["seconds"])
    most_nodes = max(rows, key=lambda r: r["nodes"])
    hardest = max(rows, key=lambda r: r["difficulty"])
    summary = {
        "counts": counts,
        "optimal_count": sum(1 for r in rows if r["optimal"]),
        "fallback_count": sum(1 for r in rows if not r["optimal"]),
        "avg_collected_pct": round(sum(r["collected_pct"] for r in rows) / len(rows), 1),
        "total_seconds": round(total_t, 2),
        "wall_seconds": round(time.time() - t_start, 2),
        "jobs": jobs,
        "slowest": {"level": slowest["level"], "seconds": slowest["seconds"]},
        "most_nodes": {"level": most_nodes["level"], "nodes": most_nodes["nodes"]},
        "hardest": {"level": hardest["level"], "difficulty": hardest["difficulty"]},
        "node_cap": args.node_cap,
    }
    meta = {"module": args.module, "levels": args.levels, "node_cap": args.node_cap}
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "meta": meta, "rows": rows}, fh,
                      ensure_ascii=False, indent=1)
        print(f"wrote {args.out}")
    if args.html and not args.no_html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(rows, summary, args.module, args.node_cap,
                                 args.levels, meta))
        print(f"wrote {args.html}")


if __name__ == "__main__":
    main()
