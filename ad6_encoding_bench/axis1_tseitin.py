"""Axis 1 (AD6_ENCODING_PLAN.md §3/§2.2): naive (ad6's own, De-Morgan +
distribute) CNF conversion vs. a standard Tseitin conversion (tseitin.py),
on the EXACT SAME formulas ad6's own pipeline builds for a real topology --
not a synthetic stand-in. Monkeypatches SATUtils.ConvertToCNF for the
duration of one build_model() call to capture each pre-CNF formula ad6
converts (one per Kripke edge, per _ConvertNodesToImplications, plus one
top-level pass in InstantiateBase) alongside how long ad6's own naive
converter took and how many clauses it produced; then runs the standalone
Tseitin converter on each captured formula for comparison. Restores the
original function afterward -- no ad6/ source file is modified, this is a
runtime-only interception in this script's own process.

Usage: PYTHONPATH=../ad6 python3 axis1_tseitin.py [n_routers] [distractors_per_router]
"""
import sys
import os
import time
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

from src.sat.satutils import SATUtils
from tseitin import TseitinConverter

_CAPTURED = []  # list of (pre_cnf_formula_copy, naive_time, naive_clause_count)
_ORIGINAL_CONVERT = SATUtils.ConvertToCNF


def _capturing_convert(Formula):
    pre_copy = deepcopy(Formula)
    t0 = time.perf_counter()
    _ORIGINAL_CONVERT(Formula)
    elapsed = time.perf_counter() - t0
    try:
        n_clauses = len(Formula[0])
    except Exception:
        n_clauses = None
    _CAPTURED.append((pre_copy, elapsed, n_clauses))


def run(n_routers, distractors_per_router):
    _CAPTURED.clear()
    SATUtils.ConvertToCNF = staticmethod(_capturing_convert)
    try:
        from gen_topology import build_model
        build_model(n_routers=n_routers,
                    distractors_per_router=distractors_per_router,
                    cyclic=False)
    finally:
        SATUtils.ConvertToCNF = _ORIGINAL_CONVERT

    total_naive_time = sum(c[1] for c in _CAPTURED)
    total_naive_clauses = sum(c[2] or 0 for c in _CAPTURED)

    total_tseitin_time = 0.0
    total_tseitin_clauses = 0
    failures = 0
    for pre_copy, _naive_time, _naive_clauses in _CAPTURED:
        conv = TseitinConverter()
        t0 = time.perf_counter()
        try:
            conv.convert_top(pre_copy)
            total_tseitin_time += time.perf_counter() - t0
            total_tseitin_clauses += len(conv.clauses)
        except Exception:
            failures += 1

    print("n_routers=%d distractors_per_router=%d -> %d ConvertToCNF call sites captured"
          % (n_routers, distractors_per_router, len(_CAPTURED)))
    if failures:
        print("  (%d formulas failed to convert via Tseitin -- see failures)" % failures)
    print("  naive  (ad6's own):  total_time=%.4fs  total_clauses=%d"
          % (total_naive_time, total_naive_clauses))
    print("  tseitin (standard):  total_time=%.4fs  total_clauses=%d"
          % (total_tseitin_time, total_tseitin_clauses))
    return {
        'n_routers': n_routers, 'distractors_per_router': distractors_per_router,
        'n_calls': len(_CAPTURED),
        'naive_time': total_naive_time, 'naive_clauses': total_naive_clauses,
        'tseitin_time': total_tseitin_time, 'tseitin_clauses': total_tseitin_clauses,
    }


def check_equisatisfiable(n_routers=4, distractors_per_router=5):
    """Sanity check: pick the largest captured formula and confirm ad6's
    naive CNF and the Tseitin CNF agree on SAT/UNSAT via the same solver."""
    from src.solver.pycosat import PycoSATAdapter
    from src.xml.xmlutils import XMLUtils

    _CAPTURED.clear()
    SATUtils.ConvertToCNF = staticmethod(_capturing_convert)
    try:
        from gen_topology import build_model
        build_model(n_routers=n_routers,
                    distractors_per_router=distractors_per_router,
                    cyclic=False)
    finally:
        SATUtils.ConvertToCNF = _ORIGINAL_CONVERT

    pre_copy, _t, _c = max(_CAPTURED, key=lambda c: len(list(c[0].iter())))

    naive_formula = deepcopy(pre_copy)
    _ORIGINAL_CONVERT(naive_formula)
    solver = PycoSATAdapter()
    naive_sat = bool(solver.Solve(naive_formula))

    conv = TseitinConverter()
    conv.convert_top(deepcopy(pre_copy))
    dimacs = conv.to_dimacs()

    import subprocess
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.cnf')
    with os.fdopen(fd, 'w') as f:
        f.write(dimacs)
    result = subprocess.run(['cadical', path], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=30)
    os.remove(path)
    tseitin_sat = b's SATISFIABLE' in result.stdout

    print("equisatisfiability check on largest captured formula: "
          "naive=%s tseitin=%s -> %s"
          % (naive_sat, tseitin_sat,
             "MATCH" if naive_sat == tseitin_sat else "MISMATCH"))
    return naive_sat == tseitin_sat


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    r = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    check_equisatisfiable()
    print()
    for rr in (10, 50, 100, 200, 400):
        run(n_routers=n, distractors_per_router=rr)
