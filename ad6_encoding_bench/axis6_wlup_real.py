"""Axis 6 (AD6_ENCODING_PLAN.md §3.6's remaining gap): test the incremental/
assumption-based solving lever against wl_up's REAL rules and REAL stateful
`<->>` queries -- not the synthetic role-count-matched proxy §3.6 used.

Builds the actual FaVe+ad6 model via the real, unmodified integration path
(fave/ad6/adapter.py's Ad6Adapter + util/in_process_driver.py's
InProcessFaVe, exactly as fave/test/test_ad6_wl_up.py does), calling
src/parser/favemodel.py's build_config/instantiate_base DIRECTLY (in-
process) instead of going through ad6/fave_bridge.py's subprocess
boundary -- so the real Kripke/CNF model is available for direct
comparison, the way every other axis in this harness works.

Queries come from the REAL bench/wl_up/cchecks.json (11902 entries, 3302
stateful per AD6_PLAN.md §1.2's table) -- NOT synthesized. Each sampled
query is answered three ways: (1) ad6 real, via
Instantiator.SolveAcyclicEndToEnd -- the actual, current production path
fave_bridge.py uses, including its src-CIDR seeding and `<->>` state
forcing; (2) Z3 fresh; (3) Z3 incremental -- same construction as every
other axis.

Read-only use of ad6/ and fave/'s existing modules (Ad6Adapter,
InProcessFaVe, favemodel, Instantiator) -- nothing there is modified. This
script lives entirely in ad6_encoding_bench/.

Usage: python3 axis6_wlup_real.py [sample_size]
(run from ad6_encoding_bench/ -- paths below are relative to this file)
"""
import sys
import os
import json
import time
import logging
from copy import deepcopy

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, '..')
FAVE_ROOT = os.path.join(_ROOT, 'fave')
AD6_ROOT = os.path.join(_ROOT, 'ad6')

sys.setrecursionlimit(10 ** 6)


def build_real_wlup():
    """Returns (engine, ir) via the real, unmodified FaVe+ad6 integration
    path -- mirrors fave/test/test_ad6_wl_up.py's setUpClass exactly, up
    to (not including) the check_compliance subprocess call."""
    sys.path.insert(0, FAVE_ROOT)
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("axis6_wlup_real")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log)

    cwd = os.getcwd()
    os.chdir(FAVE_ROOT)
    try:
        engine.load_bench_metadata("bench/wl_up")
        with InProcessFaVe(engine) as fave:
            fave.replay("bench/wl_up")
            ir = engine._build_ir()
    finally:
        os.chdir(cwd)
    return engine, ir


def capture_real_model_pre_cnf(ir):
    """Same monkeypatch trick as axis1/axis4/axis5 -- capture the LAST
    (outermost, favemodel.instantiate_base-level) pre-CNF formula. Keeps
    only the most recent capture alive at a time (not a growing list) to
    bound peak memory on this much bigger real model."""
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


def instantiate_real_model(ir):
    """favemodel.build_config/instantiate_base run with cwd=ad6/, exactly
    like fave_bridge.py's own main() -- some of ad6's file-relative
    resource loading assumes this."""
    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.xml.xmlutils import XMLUtils
    from src.core.instantiator import Instantiator

    cwd = os.getcwd()
    os.chdir(AD6_ROOT)
    try:
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, encoding = favemodel.instantiate_base(config, ir)
    finally:
        os.chdir(cwd)
    return kripke, encoding


def load_cchecks_as_queries(engine, sample_plain=150, sample_stateful=150):
    """bench/wl_up/cchecks.json's real shape (verified directly, not
    assumed): {source_name: [(probe_name, valid, cond), ...]}, 11902
    entries total. `valid` there is the OPPOSITE polarity of the
    (source, negated, cond) convention check_compliance/queries expect --
    negated = not valid (AD6_PLAN.md's own documented gotcha). Builds the
    exact same per-query dict shape Ad6Adapter.check_compliance does, so
    fave_bridge.py's own _seed_literals/_state_literals apply unmodified."""
    path = os.path.join(FAVE_ROOT, 'bench', 'wl_up', 'cchecks.json')
    with open(path) as raw:
        cchecks = json.load(raw)

    plain, stateful = [], []
    for source_name, entries in cchecks.items():
        if source_name not in engine._generators:
            continue
        for probe_name, valid, cond in entries:
            if probe_name not in engine._probes:
                continue
            q = {
                "source": source_name, "probe": probe_name,
                "src_cidr": engine._gen_src.get(source_name),
                "negated": not valid, "cond": cond or [],
            }
            (stateful if cond else plain).append(q)

    return plain[:sample_plain], stateful[:sample_stateful]


def build_instance(kripke, encoding, favemodel, q):
    from src.core.instantiator import Instantiator
    source = favemodel.gen_entry_key(q['source'])
    destination = favemodel.query_destination_key(q['probe'], ir_ref[0])
    instance = Instantiator.InstantiateEndToEnd(kripke, deepcopy(encoding), source, destination)
    if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
        instance[0].extend(bridge_ref[0]._seed_literals(q['src_cidr']))
    for literal in bridge_ref[0]._state_literals(q.get('cond')):
        instance[0].append(literal)
    return instance, source, destination


ir_ref = [None]
bridge_ref = [None]


if __name__ == '__main__':
    sample_plain = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    sample_stateful = int(sys.argv[2]) if len(sys.argv) > 2 else 150

    print("building real wl_up FaVe model (Ad6Adapter + InProcessFaVe)...")
    engine, ir = build_real_wlup()
    ir_ref[0] = ir
    print("generators=%d probes=%d devices=%d" %
          (len(engine._generators), len(engine._probes), len(ir['devices'])))

    print("\ninstantiating real ad6 Kripke/CNF model (favemodel.instantiate_base)...")
    t0 = time.perf_counter()
    kripke, encoding = instantiate_real_model(ir)
    print("build time: %.2fs, %d Kripke nodes" %
          (time.perf_counter() - t0, len(list(kripke.IterNodes()))))

    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.core.instantiator import Instantiator
    from src.solver.pycosat import PycoSATAdapter
    from src.sat.satutils import SATUtils
    from src.xml.xmlutils import XMLUtils
    import fave_bridge
    bridge_ref[0] = fave_bridge

    print("\nsampling real bench/wl_up/cchecks.json (%d plain + %d stateful requested)..."
          % (sample_plain, sample_stateful))
    plain_qs, stateful_qs = load_cchecks_as_queries(engine, sample_plain, sample_stateful)
    print("got %d plain, %d stateful (of 3302 real stateful entries, related:0/1 mixed)"
          % (len(plain_qs), len(stateful_qs)))
    queries = plain_qs + stateful_qs

    print("\n-- ad6 real (Instantiator.SolveAcyclicEndToEnd, the actual production path) --")
    solver = PycoSATAdapter()
    acyclic_cache = {}
    ad6_results = []
    escalated_count = 0
    t0 = time.perf_counter()
    for q in queries:
        instance, source, destination = build_instance(kripke, encoding, favemodel, q)
        stats = {}
        reachable = Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, source, destination, Cache=acyclic_cache, Stats=stats)
        ad6_results.append(bool(reachable))
        if stats.get('Escalated'):
            escalated_count += 1
    ad6_time = time.perf_counter() - t0
    print("ad6 real: %d queries in %.2fs (%.4fs/query), %d escalated to the CEGAR path"
          % (len(queries), ad6_time, ad6_time / len(queries), escalated_count))

    print("\ncapturing pre-CNF formula for the SAME real model (for Z3 conversion)...")
    t0 = time.perf_counter()
    kripke_z, base_xml = capture_real_model_pre_cnf(ir)
    print("captured in %.2fs" % (time.perf_counter() - t0))

    import z3
    from xml_to_z3 import to_z3

    root = base_xml[0] if base_xml.tag == XMLUtils.FORMULA else base_xml
    t0 = time.perf_counter()
    base_z3 = to_z3(root)
    print("XML->Z3 conversion: %.2fs" % (time.perf_counter() - t0))

    def z3_disjunction(node, transitions):
        return z3.Or(*[to_z3(XMLUtils.CreateTransition(*args)) for args in transitions]) \
            if transitions else z3.BoolVal(False)

    def build_assumption(q):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        f_trans = [(source, t, flag) for t, flag in kripke_z.IterFTransitions(source)]
        b_trans = [(p, destination, flag) for p, flag in kripke_z.IterBTransitions(destination)]
        parts = [z3_disjunction(source, f_trans), z3_disjunction(destination, b_trans)]
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            for lit in fave_bridge._seed_literals(q['src_cidr']):
                parts.append(to_z3(lit))
        for lit in fave_bridge._state_literals(q.get('cond')):
            parts.append(to_z3(lit))
        return z3.And(*parts)

    print("\nbuilding %d Z3 assumption terms..." % len(queries))
    t0 = time.perf_counter()
    assumptions = [build_assumption(q) for q in queries]
    print("built in %.2fs" % (time.perf_counter() - t0))

    print("\n-- Z3 fresh (no incremental reuse) --")
    t0 = time.perf_counter()
    z3_fresh_results = []
    for a in assumptions:
        s = z3.Solver()
        s.add(base_z3)
        z3_fresh_results.append(str(s.check(a)) == 'sat')
    z3_fresh_time = time.perf_counter() - t0
    print("Z3 fresh: %d queries in %.4fs (%.5fs/query)"
          % (len(queries), z3_fresh_time, z3_fresh_time / len(queries)))

    print("\n-- Z3 incremental (one persistent solver) --")
    t0 = time.perf_counter()
    solver_incr = z3.Solver()
    solver_incr.add(base_z3)
    z3_incr_results = [str(solver_incr.check(a)) == 'sat' for a in assumptions]
    z3_incr_time = time.perf_counter() - t0
    print("Z3 incremental: %d queries in %.4fs (%.5fs/query)"
          % (len(queries), z3_incr_time, z3_incr_time / len(queries)))

    print("\n-- correctness: ad6 real vs. Z3 incremental --")
    print("match:", ad6_results == z3_incr_results)
    if ad6_results != z3_incr_results:
        mismatches = [(q['source'], q['probe'], q['cond'], a, b)
                      for q, a, b in zip(queries, ad6_results, z3_incr_results) if a != b]
        print("MISMATCHES (%d):" % len(mismatches))
        for m in mismatches[:10]:
            print(" ", m)

    print("\n-- summary --")
    print("ad6 real:        %8.3fs  (%.5fs/query)" % (ad6_time, ad6_time / len(queries)))
    print("Z3 fresh:        %8.3fs  (%.5fs/query)" % (z3_fresh_time, z3_fresh_time / len(queries)))
    print("Z3 incremental:  %8.3fs  (%.5fs/query)" % (z3_incr_time, z3_incr_time / len(queries)))
