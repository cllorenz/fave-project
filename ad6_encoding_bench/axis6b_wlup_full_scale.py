"""Axis 6, scaled (AD6_ENCODING_PLAN.md §3.7's own open item): §3.7 tested
100 of bench/wl_up/cchecks.json's 11,902 real queries. This scales up:

- ad6-real and Z3-fresh: measured on a larger sample than §3.7 (for a more
  statistically solid per-query rate), then EXTRAPOLATED to the full
  11,902 -- a full ad6-real run at §3.7's ~1.36s/query rate is ~4.5 hours,
  not something to literally run mid-session.
- Z3 incremental: run for REAL on essentially the ENTIRE real cchecks.json
  (every entry whose source/probe survived the real FaVe model build),
  not extrapolated -- its own §3.7 rate (~0.018s/query) implies well
  under 5 minutes for all ~11,902, which is exactly what makes this the
  one worth actually measuring in full rather than projecting.

Reuses ad6_encoding_bench/axis6_wlup_real.py's model-building and
query-loading functions unmodified (same real, unmodified FaVe+ad6
integration path; nothing in ad6/ or fave/ is touched).

Usage: python3 axis6b_wlup_full_scale.py [sample_size]
(run from ad6_encoding_bench/)
"""
import sys
import os
import json
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from axis6_wlup_real import (
    build_real_wlup, instantiate_real_model, capture_real_model_pre_cnf,
    FAVE_ROOT, AD6_ROOT,
)


def load_all_cchecks_as_queries(engine):
    """Every real cchecks.json entry whose source/probe survived the real
    model build -- the full, unsampled query set (same polarity-flip
    gotcha as axis6_wlup_real.load_cchecks_as_queries, documented there)."""
    path = os.path.join(FAVE_ROOT, 'bench', 'wl_up', 'cchecks.json')
    with open(path) as raw:
        cchecks = json.load(raw)

    queries = []
    for source_name, entries in cchecks.items():
        if source_name not in engine._generators:
            continue
        for probe_name, valid, cond in entries:
            if probe_name not in engine._probes:
                continue
            queries.append({
                "source": source_name, "probe": probe_name,
                "src_cidr": engine._gen_src.get(source_name),
                "negated": not valid, "cond": cond or [],
            })
    return queries


if __name__ == '__main__':
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 300

    print("building real wl_up FaVe model...")
    engine, ir = build_real_wlup()
    print("generators=%d probes=%d devices=%d" %
          (len(engine._generators), len(engine._probes), len(ir['devices'])))

    all_queries = load_all_cchecks_as_queries(engine)
    n_stateful = sum(1 for q in all_queries if q['cond'])
    print("full real query set: %d total (%d stateful, %d plain)"
          % (len(all_queries), n_stateful, len(all_queries) - n_stateful))

    # interleave plain/stateful for the sample so it's representative, not
    # front-loaded with whichever category cchecks.json happens to list first
    plain = [q for q in all_queries if not q['cond']]
    stateful = [q for q in all_queries if q['cond']]
    half = sample_size // 2
    sample = []
    for i in range(half):
        if i < len(plain):
            sample.append(plain[i])
        if i < len(stateful):
            sample.append(stateful[i])
    sample = sample[:sample_size]
    print("\nad6-real/Z3-fresh measurement sample: %d queries (%d stateful)"
          % (len(sample), sum(1 for q in sample if q['cond'])))

    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.core.instantiator import Instantiator
    from src.solver.pycosat import PycoSATAdapter
    from src.xml.xmlutils import XMLUtils
    import fave_bridge
    from copy import deepcopy

    print("\ninstantiating real ad6 Kripke/CNF model...")
    t0 = time.perf_counter()
    kripke, encoding = instantiate_real_model(ir)
    print("build time: %.2fs, %d Kripke nodes" %
          (time.perf_counter() - t0, len(list(kripke.IterNodes()))))

    def build_instance(q):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, deepcopy(encoding), source, destination)
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            instance[0].extend(fave_bridge._seed_literals(q['src_cidr']))
        for literal in fave_bridge._state_literals(q.get('cond')):
            instance[0].append(literal)
        return instance, source, destination

    print("\n-- ad6 real, measured sample (%d queries) --" % len(sample))
    solver = PycoSATAdapter()
    acyclic_cache = {}
    ad6_results = []
    escalated = 0
    t0 = time.perf_counter()
    for q in sample:
        instance, source, destination = build_instance(q)
        stats = {}
        reachable = Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, source, destination, Cache=acyclic_cache, Stats=stats)
        ad6_results.append(bool(reachable))
        if stats.get('Escalated'):
            escalated += 1
    ad6_sample_time = time.perf_counter() - t0
    ad6_rate = ad6_sample_time / len(sample)
    print("ad6 real: %d queries in %.2fs (%.4fs/query), %d escalated"
          % (len(sample), ad6_sample_time, ad6_rate, escalated))
    print("EXTRAPOLATED to full %d: %.1fs (%.1f min / %.2f hr)"
          % (len(all_queries), ad6_rate * len(all_queries),
             ad6_rate * len(all_queries) / 60, ad6_rate * len(all_queries) / 3600))

    print("\ncapturing pre-CNF formula for Z3 conversion...")
    t0 = time.perf_counter()
    kripke_z, base_xml = capture_real_model_pre_cnf(ir)
    print("captured in %.2fs" % (time.perf_counter() - t0))

    import z3
    from xml_to_z3 import to_z3

    root = base_xml[0] if base_xml.tag == XMLUtils.FORMULA else base_xml
    t0 = time.perf_counter()
    base_z3 = to_z3(root)
    print("XML->Z3 conversion: %.2fs" % (time.perf_counter() - t0))

    def z3_disjunction(transitions):
        return z3.Or(*[to_z3(XMLUtils.CreateTransition(*args)) for args in transitions]) \
            if transitions else z3.BoolVal(False)

    def build_assumption(q):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        f_trans = [(source, t, flag) for t, flag in kripke_z.IterFTransitions(source)]
        b_trans = [(p, destination, flag) for p, flag in kripke_z.IterBTransitions(destination)]
        parts = [z3_disjunction(f_trans), z3_disjunction(b_trans)]
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            for lit in fave_bridge._seed_literals(q['src_cidr']):
                parts.append(to_z3(lit))
        for lit in fave_bridge._state_literals(q.get('cond')):
            parts.append(to_z3(lit))
        return z3.And(*parts)

    print("\nbuilding %d Z3 assumption terms for the sample (Z3-fresh)..." % len(sample))
    t0 = time.perf_counter()
    sample_assumptions = [build_assumption(q) for q in sample]
    print("built in %.2fs" % (time.perf_counter() - t0))

    print("\n-- Z3 fresh, measured sample --")
    t0 = time.perf_counter()
    z3_fresh_results = []
    for a in sample_assumptions:
        s = z3.Solver()
        s.add(base_z3)
        z3_fresh_results.append(str(s.check(a)) == 'sat')
    z3_fresh_time = time.perf_counter() - t0
    z3_fresh_rate = z3_fresh_time / len(sample)
    print("Z3 fresh: %d queries in %.2fs (%.4fs/query)" % (len(sample), z3_fresh_time, z3_fresh_rate))
    print("EXTRAPOLATED to full %d: %.1fs (%.1f min)"
          % (len(all_queries), z3_fresh_rate * len(all_queries), z3_fresh_rate * len(all_queries) / 60))

    print("\n-- correctness: ad6 real vs Z3 fresh on the sample --")
    print("match:", ad6_results == z3_fresh_results)

    print("\n-- Z3 incremental: ACTUALLY RUN on the FULL real query set (%d queries) --"
          % len(all_queries))
    t0 = time.perf_counter()
    all_assumptions = [build_assumption(q) for q in all_queries]
    print("built all %d assumption terms in %.2fs" % (len(all_assumptions), time.perf_counter() - t0))

    t0 = time.perf_counter()
    solver_incr = z3.Solver()
    solver_incr.add(base_z3)
    incr_results_full = [str(solver_incr.check(a)) == 'sat' for a in all_assumptions]
    z3_incr_full_time = time.perf_counter() - t0
    print("Z3 incremental FULL RUN: %d queries in %.2fs (%.1f min) -- %.6fs/query average"
          % (len(all_queries), z3_incr_full_time, z3_incr_full_time / 60,
             z3_incr_full_time / len(all_queries)))

    print("\n-- correctness: ad6 real (sample) vs Z3 incremental (same indices in full run) --")
    # the sample's queries are a subset of all_queries; find their positions
    # in the full run's results by identity of (source, probe, cond)
    index_by_key = {}
    for i, q in enumerate(all_queries):
        index_by_key.setdefault((q['source'], q['probe'], json.dumps(q['cond'])), i)
    incr_sample_results = [
        incr_results_full[index_by_key[(q['source'], q['probe'], json.dumps(q['cond']))]]
        for q in sample
    ]
    match = ad6_results == incr_sample_results
    print("match:", match)
    if not match:
        mism = [(q['source'], q['probe'], q['cond'])
                for q, a, b in zip(sample, ad6_results, incr_sample_results) if a != b]
        print("mismatches (%d):" % len(mism), mism[:10])

    print("\n-- SUMMARY --")
    print("total real queries: %d (%d stateful, %d plain)"
          % (len(all_queries), n_stateful, len(all_queries) - n_stateful))
    print("ad6 real        (extrapolated from %d-sample): %8.1fs (%.2f hr)"
          % (len(sample), ad6_rate * len(all_queries), ad6_rate * len(all_queries) / 3600))
    print("Z3 fresh        (extrapolated from %d-sample): %8.1fs (%.1f min)"
          % (len(sample), z3_fresh_rate * len(all_queries), z3_fresh_rate * len(all_queries) / 60))
    print("Z3 incremental  (MEASURED, full run):          %8.1fs (%.1f min)"
          % (z3_incr_full_time, z3_incr_full_time / 60))
