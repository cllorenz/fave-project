"""Axis 8 follow-up (2026-08-26/27): axis8_stanford_incremental.py's first full
run (with ulimit -s unlimited, after the first attempt died silently -- a
C-stack overflow from sys.setrecursionlimit(10**6) + the default 8MB stack,
confirmed by this fix) got real ad6-real ground truth (5 queries, 2
escalated at 2164.64s/2259.70s, matching B1's 7.7-2923s historical range)
but then stalled inside the (unlogged, per-query-silent) Z3-fresh loop for
the full 256 queries and was killed at the 90-minute cap before reaching
Z3-incremental -- the actually-interesting number.

This script skips re-running the expensive ad6-real sample (reusing the
known-good 5 results below as ground truth) and reorders to get
Z3-INCREMENTAL FIRST (the real question), with per-N-query progress
logging this time so a slow run is at least visible. Z3-fresh only gets a
small control sample, not the full 256.

Run with `ulimit -s unlimited` first, same as the run that got past the
crash. Usage: python3 -u axis8b_stanford_incremental_only.py [z3_incr_n] [z3_fresh_n]
"""
import sys
import os
import time
import logging
from copy import deepcopy

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, '..')
FAVE_ROOT = os.path.join(_ROOT, 'fave')
AD6_ROOT = os.path.join(_ROOT, 'ad6')

sys.setrecursionlimit(10 ** 6)

_PREFIX = "bench/wl_stanford/stanford-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}

# From axis8_stanford_incremental.py's first successful (unlimited-stack) run,
# in exact query order (queries = [{"source": s, "probe": p} for p in probes
# for s in sources], both sorted -- deterministic).
KNOWN_AD6_REAL = [True, False, False, True, True]


def build_real_stanford():
    sys.path.insert(0, FAVE_ROOT)
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("axis8b_stanford")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log)

    cwd = os.getcwd()
    os.chdir(FAVE_ROOT)
    try:
        with InProcessFaVe(engine) as fave:
            fave.replay(_PREFIX, files=_FILES)
            ir = engine._build_ir()
            sources = sorted(engine._generators)
            probes = sorted(engine._probes)
    finally:
        os.chdir(cwd)
    return engine, ir, sources, probes


def capture_real_model_pre_cnf(ir):
    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.xml.xmlutils import XMLUtils
    from src.sat.satutils import SATUtils

    original = SATUtils.ConvertToCNF
    last = [None]

    def _capturing(Formula):
        last[0] = deepcopy(Formula)
        original(Formula)

    cwd = os.getcwd()
    os.chdir(AD6_ROOT)
    try:
        SATUtils.ConvertToCNF = staticmethod(_capturing)
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, _encoding = favemodel.instantiate_base(config, ir)
    finally:
        SATUtils.ConvertToCNF = original
        os.chdir(cwd)
    return kripke, last[0]


if __name__ == '__main__':
    z3_incr_n = int(sys.argv[1]) if len(sys.argv) > 1 else 256
    z3_fresh_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    print("building real wl_stanford FaVe model (Ad6Adapter + InProcessFaVe)...", flush=True)
    t0 = time.perf_counter()
    engine, ir, sources, probes = build_real_stanford()
    print("build_real_stanford: %.2fs, sources=%d probes=%d devices=%d" %
          (time.perf_counter() - t0, len(sources), len(probes), len(ir['devices'])), flush=True)

    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.core.instantiator import Instantiator
    from src.xml.xmlutils import XMLUtils

    queries = [{"source": s, "probe": p} for p in probes for s in sources]
    print("%d total (source, probe) pairs" % len(queries), flush=True)

    print("\ncapturing pre-CNF base formula (favemodel.instantiate_base, monkeypatched)...", flush=True)
    t0 = time.perf_counter()
    kripke_z, base_xml = capture_real_model_pre_cnf(ir)
    print("captured in %.2fs" % (time.perf_counter() - t0), flush=True)

    print("\nbuilding SCC-scoped acyclic rank constraints ONCE (Instantiator._CreateAcyclicConstraints)...", flush=True)
    t0 = time.perf_counter()
    acyclic_constraints_z = Instantiator._CreateAcyclicConstraints(kripke_z)
    print("rank-constraint build: %.2fs, %d extra clauses" %
          (time.perf_counter() - t0, len(acyclic_constraints_z)), flush=True)

    import z3
    from xml_to_z3 import to_z3

    root = base_xml[0] if base_xml.tag == XMLUtils.FORMULA else base_xml
    print("\nconverting base XML -> Z3...", flush=True)
    t0 = time.perf_counter()
    base_z3 = to_z3(root)
    print("base XML->Z3: %.2fs" % (time.perf_counter() - t0), flush=True)

    print("converting %d rank-constraint clauses -> Z3..." % len(acyclic_constraints_z), flush=True)
    t0 = time.perf_counter()
    rank_z3_terms = [to_z3(c) for c in acyclic_constraints_z]
    print("rank clauses XML->Z3: %.2fs" % (time.perf_counter() - t0), flush=True)

    full_base_z3 = z3.And(base_z3, *rank_z3_terms)

    def z3_disjunction(node, transitions):
        return z3.Or(*[to_z3(XMLUtils.CreateTransition(*args)) for args in transitions]) \
            if transitions else z3.BoolVal(False)

    def build_assumption(q):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        f_trans = [(source, t, flag) for t, flag in kripke_z.IterFTransitions(source)]
        b_trans = [(p, destination, flag) for p, flag in kripke_z.IterBTransitions(destination)]
        parts = [z3_disjunction(source, f_trans), z3_disjunction(destination, b_trans)]
        return z3.And(*parts)

    print("\nbuilding %d Z3 assumption terms..." % len(queries), flush=True)
    t0 = time.perf_counter()
    assumptions = [build_assumption(q) for q in queries]
    print("built in %.2fs" % (time.perf_counter() - t0), flush=True)

    print("\n-- Z3 INCREMENTAL (ONE persistent solver, base+rank built ONCE) -- THE KEY NUMBER --", flush=True)
    t0 = time.perf_counter()
    solver_incr = z3.Solver()
    solver_incr.add(full_base_z3)
    build_once_time = time.perf_counter() - t0
    print("(base+rank load into persistent solver: %.2fs)" % build_once_time, flush=True)

    incr_n = min(z3_incr_n, len(assumptions))
    z3_incr_results = []
    t0 = time.perf_counter()
    for i, a in enumerate(assumptions[:incr_n], start=1):
        z3_incr_results.append(str(solver_incr.check(a)) == 'sat')
        if i % 20 == 0 or i == incr_n:
            elapsed = time.perf_counter() - t0
            print("  [%d/%d] elapsed %.2fs (%.4fs/query so far)" %
                  (i, incr_n, elapsed, elapsed / i), flush=True)
    z3_incr_time = time.perf_counter() - t0
    print("Z3 incremental: %d queries in %.4fs (%.5fs/query)"
          % (incr_n, z3_incr_time, z3_incr_time / incr_n), flush=True)

    print("\n-- correctness: known ad6-real (5 queries, from the prior run) vs Z3 incremental (same order) --", flush=True)
    n_check = min(5, incr_n)
    mismatches = [(i, KNOWN_AD6_REAL[i], z3_incr_results[i]) for i in range(n_check)
                  if KNOWN_AD6_REAL[i] != z3_incr_results[i]]
    print("compared %d pairs, %d mismatches" % (n_check, len(mismatches)), flush=True)
    for m in mismatches:
        print("  MISMATCH:", queries[m[0]], m, flush=True)

    print("\n-- Z3 fresh (base + rank constraints, NO reuse) -- small control sample only --", flush=True)
    fresh_n = min(z3_fresh_n, len(assumptions))
    z3_fresh_results = []
    t0 = time.perf_counter()
    for i, a in enumerate(assumptions[:fresh_n], start=1):
        s = z3.Solver()
        s.add(full_base_z3)
        z3_fresh_results.append(str(s.check(a)) == 'sat')
        print("  [%d/%d] elapsed %.2fs" % (i, fresh_n, time.perf_counter() - t0), flush=True)
    z3_fresh_time = time.perf_counter() - t0
    print("Z3 fresh: %d queries in %.4fs (%.5fs/query)"
          % (fresh_n, z3_fresh_time, z3_fresh_time / fresh_n), flush=True)

    print("\n-- SUMMARY --", flush=True)
    print("known ad6-real (prior run):  5 queries, 2 escalated at 2164.64s/2259.70s, 3 fast-path <1s", flush=True)
    print("Z3 base+rank one-time build: %.2fs (pre-CNF capture + rank build + XML->Z3 + assumption terms)" %
          build_once_time, flush=True)
    print("Z3 incremental:              %8.3fs over %d queries (%.5fs/query)"
          % (z3_incr_time, incr_n, z3_incr_time / incr_n), flush=True)
    print("Z3 fresh (control sample):   %8.3fs over %d queries (%.5fs/query)"
          % (z3_fresh_time, fresh_n, z3_fresh_time / fresh_n), flush=True)
    if incr_n == len(queries):
        print("Z3 incremental covers ALL %d real Stanford source->probe pairs." % len(queries), flush=True)
