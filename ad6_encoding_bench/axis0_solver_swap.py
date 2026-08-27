"""Axis 0 (AD6_ENCODING_PLAN.md §3): solver-engine swap, ZERO encoding
change. Takes the exact DIMACS CNF ad6's own pipeline produces for a real
InstantiateReach query (via AbstractSolver._ConvertToDIMACSStr, the same
method MiniSATAdapter/ClaspAdapter already use) and times it through
several solver binaries: the two ad6 ships (minisat, clasp) plus two modern
CDCL engines (cadical, cryptominisat5) not available in 2014-2015.

Usage: PYTHONPATH=../ad6 python3 axis0_solver_swap.py [max_n]
"""
import sys
import os
import time
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

from src.core.instantiator import Instantiator
from src.solver.minisat import MiniSATAdapter

from gen_topology import build_model

SOLVERS = {
    'minisat (2010, ad6-native)': ['minisat', '{in}', '{out}'],
    'clasp (2012, ad6-native)': ['clasp', '1', '{in}'],
    'cadical (2023, modern CDCL)': ['cadical', '{in}'],
    'cryptominisat5 (2023, modern CDCL)': ['cryptominisat5', '{in}'],
}


def to_dimacs(instance):
    # _ConvertToDIMACSStr is a plain AbstractSolver method, independent of
    # which adapter subclass calls it -- MiniSATAdapter is just a
    # convenient concrete instance.
    adapter = MiniSATAdapter()
    _variables, dimacs = adapter._ConvertToDIMACSStr(instance)
    return dimacs


def time_solver(name, argv_template, cnf_path):
    argv = [a.replace('{in}', cnf_path) for a in argv_template]
    out_path = None
    if '{out}' in ' '.join(argv_template):
        out_fd, out_path = tempfile.mkstemp(suffix='.out')
        os.close(out_fd)
        argv = [a.replace('{out}', out_path) for a in argv]

    start = time.perf_counter()
    try:
        subprocess.run(argv, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=120)
        elapsed = time.perf_counter() - start
    except FileNotFoundError:
        elapsed = None
    finally:
        if out_path and os.path.exists(out_path):
            os.remove(out_path)
    return elapsed


def run(n_routers, distractors_per_router):
    kripke, encoding, entry_key, accept_key = build_model(
        n_routers=n_routers, distractors_per_router=distractors_per_router,
        cyclic=False)
    instance = Instantiator.InstantiateReach(kripke, encoding, accept_key)
    dimacs = to_dimacs(instance)

    header = dimacs.splitlines()[0]
    n_vars, n_clauses = header.split()[2], header.split()[3]

    fd, cnf_path = tempfile.mkstemp(suffix='.cnf')
    with os.fdopen(fd, 'w') as f:
        f.write(dimacs)

    row = {'n_routers': n_routers,
           'distractors_per_router': distractors_per_router,
           'n_vars': n_vars, 'n_clauses': n_clauses}
    for name, argv_template in SOLVERS.items():
        row[name] = time_solver(name, argv_template, cnf_path)

    os.remove(cnf_path)
    return row


if __name__ == '__main__':
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    sizes = sorted(set([4, 8, 16] + [n for n in range(20, max_n + 1, 20)]))

    print(f"{'N':>4} {'R/hop':>6} {'#vars':>8} {'#clauses':>9}", end='')
    for name in SOLVERS:
        print(f" {name:>28}", end='')
    print()

    for n in sizes:
        if n > max_n:
            continue
        row = run(n_routers=n, distractors_per_router=10)
        print(f"{row['n_routers']:>4} {row['distractors_per_router']:>6} "
              f"{row['n_vars']:>8} {row['n_clauses']:>9}", end='')
        for name in SOLVERS:
            t = row[name]
            print(f" {('%.4fs' % t) if t is not None else 'N/A':>28}", end='')
        print()
