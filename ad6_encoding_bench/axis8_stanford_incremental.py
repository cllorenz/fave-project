"""Axis 8 (2026-08-25 integration follow-up, AD6_PLAN.md §6's open item):
does the incremental lever survive real cyclic-topology rank-constraint
escalation cost, not just wl_up's escalation-free case (axis6/7 measured
zero escalations there)?

wl_stanford's B1 differential (AD6_PLAN.md §5.4 Stage B) is a pure
wall-clock NO-GO on Instantiator.SolveAcyclicEndToEnd: 6h budget, 74/256
(28.9%) completed, 40 of those needed the CEGAR/rank-constraint escalation
path at 7.7s-2923s EACH -- because ad6's current architecture rebuilds and
re-solves from scratch on EVERY CEGAR iteration, not just every query.

Design: rather than re-implementing CEGAR's iterative witness-blocking
loop, build the SCC-scoped acyclic rank constraints (the SAME
Instantiator._CreateAcyclicConstraints ad6's own escalation path uses) ONCE
and bake them into the incremental solver's persistent base -- this is
sound by construction per that function's own docstring (proven via a
PLAIN solve on the synthetic fixture; CEGAR is only a defensive backstop,
not structurally required). If baking them in unconditionally is cheap
when paid ONCE across many queries (as opposed to ad6's current per-query
rebuild), every query becomes a single incremental assumption-check, no
escalation branch needed at all.

Read-only use of ad6/ and fave/'s existing modules -- nothing modified.
Mirrors fave/test/test_ad6_wl_stanford.py's setUpClass exactly, stopping
before its check_compliance call (which would run the full many-hour
subprocess differential).

Usage: python3 -u axis8_stanford_incremental.py [ad6_real_sample] [z3_sample]
(run from ad6_encoding_bench/; ad6_real_sample kept small by default --
see the module docstring on why)
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


def build_real_stanford():
    """Mirrors fave/test/test_ad6_wl_stanford.py's setUpClass, stopping
    before check_compliance (the many-hour subprocess differential)."""
    sys.path.insert(0, FAVE_ROOT)
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("axis8_stanford")
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


def instantiate_real_model(ir):
    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.xml.xmlutils import XMLUtils

    cwd = os.getcwd()
    os.chdir(AD6_ROOT)
    try:
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, encoding = favemodel.instantiate_base(config, ir)
    finally:
        os.chdir(cwd)
    return kripke, encoding


def capture_real_model_pre_cnf(ir):
    """Same monkeypatch trick as axis6 -- capture the pre-CNF base formula
    for Z3 conversion, alongside a second, fresh Kripke build (Instantiator
    mutates lxml elements in place across calls in ways that make reusing
    one Kripke object across two separate encode passes risky)."""
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
    ad6_real_sample = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    z3_sample = int(sys.argv[2]) if len(sys.argv) > 2 else 256

    print("building real wl_stanford FaVe model (Ad6Adapter + InProcessFaVe)...", flush=True)
    t0 = time.perf_counter()
    engine, ir, sources, probes = build_real_stanford()
    print("build_real_stanford: %.2fs, sources=%d probes=%d devices=%d" %
          (time.perf_counter() - t0, len(sources), len(probes), len(ir['devices'])), flush=True)

    print("\ninstantiating real ad6 Kripke/CNF model (favemodel.instantiate_base)...", flush=True)
    t0 = time.perf_counter()
    kripke, encoding = instantiate_real_model(ir)
    print("build time: %.2fs, %d Kripke nodes" %
          (time.perf_counter() - t0, len(list(kripke.IterNodes()))), flush=True)

    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.core.instantiator import Instantiator
    from src.solver.pycosat import PycoSATAdapter
    from src.xml.xmlutils import XMLUtils
    import fave_bridge

    print("\ncomputing SCCs on the real 16-router topology (Instantiator._ComputeSCCs)...", flush=True)
    t0 = time.perf_counter()
    scc_of, non_trivial = Instantiator._ComputeSCCs(kripke)
    n_nodes = len(list(kripke.IterNodes()))
    n_in_nontrivial = sum(1 for scc in scc_of.values() if scc in non_trivial)
    print("SCC compute: %.2fs -- %d/%d nodes (%.1f%%) in a non-trivial SCC (cf. B1's 86%% at 3-router scale)"
          % (time.perf_counter() - t0, n_in_nontrivial, n_nodes,
             100.0 * n_in_nontrivial / n_nodes if n_nodes else 0.0), flush=True)

    print("\nbuilding SCC-scoped acyclic rank constraints ONCE (Instantiator._CreateAcyclicConstraints)...", flush=True)
    t0 = time.perf_counter()
    acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
    print("rank-constraint build: %.2fs, %d extra clauses" %
          (time.perf_counter() - t0, len(acyclic_constraints)), flush=True)

    # Build the query list exactly like test_ad6_wl_stanford.py's setUpClass
    # (all source x probe pairs, plain/non-stateful, k=1).
    queries = [{"source": s, "probe": p} for p in probes for s in sources]
    print("\n%d total (source, probe) pairs (16x16 all-pairs, matches AD6_PLAN.md's 256)" % len(queries), flush=True)

    print("\n-- ad6 real (Instantiator.SolveAcyclicEndToEnd, the actual production path) --", flush=True)
    print("(sample size kept small deliberately -- B1 measured 7.7s-2923s PER ESCALATED query "
          "on this exact topology; this is the expensive, ground-truth-correctness baseline, not "
          "the number this axis is trying to make fast)", flush=True)
    solver = PycoSATAdapter()
    acyclic_cache = {}
    ad6_results = {}
    escalated_count = 0
    t0 = time.perf_counter()
    for i, q in enumerate(queries[:ad6_real_sample], start=1):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, deepcopy(encoding), source, destination)
        stats = {}
        qt0 = time.perf_counter()
        reachable = Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, source, destination, Cache=acyclic_cache, Stats=stats)
        qdt = time.perf_counter() - qt0
        ad6_results[(q['source'], q['probe'])] = bool(reachable)
        if stats.get('Escalated'):
            escalated_count += 1
        print("  [%d/%d] %s -> %s: reachable=%s (%s, %.2fs)" %
              (i, ad6_real_sample, q['source'], q['probe'], reachable,
               "escalated" if stats.get('Escalated') else "fast-path", qdt), flush=True)
    ad6_time = time.perf_counter() - t0
    print("ad6 real: %d queries in %.2fs (%.4fs/query), %d escalated to the CEGAR path"
          % (ad6_real_sample, ad6_time, ad6_time / ad6_real_sample, escalated_count), flush=True)

    print("\ncapturing pre-CNF formula for the SAME real model (for Z3 conversion)...", flush=True)
    t0 = time.perf_counter()
    kripke_z, base_xml = capture_real_model_pre_cnf(ir)
    print("captured in %.2fs" % (time.perf_counter() - t0), flush=True)

    print("\nbuilding SCC-scoped rank constraints on the SECOND kripke build (for Z3)...", flush=True)
    t0 = time.perf_counter()
    acyclic_constraints_z = Instantiator._CreateAcyclicConstraints(kripke_z)
    print("rank-constraint build (2nd copy): %.2fs, %d extra clauses" %
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

    z3_queries = queries[:z3_sample]
    print("\nbuilding %d Z3 assumption terms..." % len(z3_queries), flush=True)
    t0 = time.perf_counter()
    assumptions = [build_assumption(q) for q in z3_queries]
    print("built in %.2fs" % (time.perf_counter() - t0), flush=True)

    print("\n-- Z3 fresh (base + rank constraints, no incremental reuse) --", flush=True)
    t0 = time.perf_counter()
    z3_fresh_results = []
    for a in assumptions:
        s = z3.Solver()
        s.add(full_base_z3)
        z3_fresh_results.append(str(s.check(a)) == 'sat')
    z3_fresh_time = time.perf_counter() - t0
    print("Z3 fresh: %d queries in %.4fs (%.5fs/query)"
          % (len(z3_queries), z3_fresh_time, z3_fresh_time / len(z3_queries)), flush=True)

    print("\n-- Z3 incremental (ONE persistent solver, base+rank built ONCE) --", flush=True)
    t0 = time.perf_counter()
    solver_incr = z3.Solver()
    solver_incr.add(full_base_z3)
    build_once_time = time.perf_counter() - t0
    print("(base+rank load into persistent solver: %.2fs)" % build_once_time, flush=True)
    t0 = time.perf_counter()
    z3_incr_results = [str(solver_incr.check(a)) == 'sat' for a in assumptions]
    z3_incr_time = time.perf_counter() - t0
    print("Z3 incremental: %d queries in %.4fs (%.5fs/query)"
          % (len(z3_queries), z3_incr_time, z3_incr_time / len(z3_queries)), flush=True)

    print("\n-- correctness: ad6 real (sample) vs. Z3 incremental (same pairs) --", flush=True)
    overlap = [(q['source'], q['probe']) for q in z3_queries[:ad6_real_sample]]
    mismatches = []
    for i, key in enumerate(overlap):
        if key in ad6_results and ad6_results[key] != z3_incr_results[i]:
            mismatches.append((key, ad6_results[key], z3_incr_results[i]))
    print("compared %d overlapping pairs, %d mismatches" % (len(overlap), len(mismatches)), flush=True)
    for m in mismatches[:10]:
        print("  MISMATCH:", m, flush=True)

    print("\n-- summary --", flush=True)
    print("ad6 real sample:      %8.3fs over %d queries (%.4fs/query), %d escalated"
          % (ad6_time, ad6_real_sample, ad6_time / ad6_real_sample, escalated_count), flush=True)
    print("Z3 fresh:              %8.3fs over %d queries (%.5fs/query)"
          % (z3_fresh_time, len(z3_queries), z3_fresh_time / len(z3_queries)), flush=True)
    print("Z3 incremental:        %8.3fs over %d queries (%.5fs/query), one-time base+rank build %.2fs"
          % (z3_incr_time, len(z3_queries), z3_incr_time / len(z3_queries), build_once_time), flush=True)
    if ad6_real_sample:
        extrapolated_full = (ad6_time / ad6_real_sample) * len(queries)
        print("EXTRAPOLATED ad6-real for all %d pairs: %.1fs (%.2f hr)"
              % (len(queries), extrapolated_full, extrapolated_full / 3600.0), flush=True)
