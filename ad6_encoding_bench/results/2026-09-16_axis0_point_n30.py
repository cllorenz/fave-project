"""Reproduce AD6_ENCODING_PLAN.md 3.1's actual Axis 0 comparison point.

axis0_solver_swap.py's own main() sweeps N at a fixed R=10/hop, which is far
too small to separate the engines (everything lands at ~4-8ms, i.e. process
startup). 3.1's published row is n_routers=30, R=200/hop (~24k vars, 63k
clauses) -- reached by calling run() directly, which is what this does.
Repeats each point so a single noisy process launch cannot carry the result.
"""
import sys, statistics
sys.path.insert(0, '/home/clorenz/fave-project/ad6_encoding_bench')
from axis0_solver_swap import run, SOLVERS

REPEATS = 5
for (n, r) in ((30, 200), (30, 400)):
    rows = [run(n_routers=n, distractors_per_router=r) for _ in range(REPEATS)]
    print("n_routers=%d R/hop=%d  %s vars, %s clauses  (%d repeats)"
          % (n, r, rows[0]['n_vars'], rows[0]['n_clauses'], REPEATS))
    for name in SOLVERS:
        ts = [row[name] for row in rows if row[name] is not None]
        if not ts:
            print("  %-36s N/A" % name); continue
        print("  %-36s median %.4fs  min %.4fs  max %.4fs"
              % (name, statistics.median(ts), min(ts), max(ts)))
    print()
