"""Axis 5 at wl_up scale (AD6_ENCODING_PLAN.md §3.5's own open gap): does
the cross-source incremental amortization still hold at n approx 137 --
the real role count of FaVe's wl_up benchmark (AD6_PLAN.md §1.3) -- with a
genuine full n*(n-1) all-pairs matrix (~18.6k pairs), not axis5's K=15
(210 pairs) sample?

Practical note: AD6_PLAN.md §5.1 documents ad6's real, measured rate on
the ACTUAL wl_up model at ~0.5s/query (a 137-query batch against one
probe took ~67s there); a full n*(n-1) sweep at that rate would take
hours -- not run literally here. Instead: ad6-real and Z3-fresh are
measured on a SAMPLE at this same n=137 base and their (already
well-established, linear-in-query-count per Axes 4-5) per-pair rate is
used to EXTRAPOLATE to the full matrix, clearly labeled as such. Z3
incremental is run for real, at the full ~18.6k pairs, since it's the
one actually likely to finish quickly -- the whole point of this test.

Also precomputes per-node disjunctions ONCE (2*n conversions) rather than
reconverting per pair (axis5_cross_source.py's simpler approach does not
scale to 18.6k pairs) -- a pair's assumption is just
And(out_disjunction[source], in_disjunction[dest]), cheap Python-level
composition of already-built Z3 terms.

Usage: PYTHONPATH=../ad6 python3 axis5b_wlup_scale.py
"""
import sys
import os
import time
import math
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

import z3

from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter
from src.xml.xmlutils import XMLUtils

from axis4_incremental import build_model, query_node_keys, _capture_base_formula
from xml_to_z3 import to_z3

N = 137


def precompute_disjunctions(kripke, nodes):
    out_disj = {}
    in_disj = {}
    for node in nodes:
        f_transitions = list(kripke.IterFTransitions(node))
        out_disj[node] = z3.Or(*[
            to_z3(XMLUtils.CreateTransition(node, t, flag)) for t, flag in f_transitions
        ]) if f_transitions else z3.BoolVal(False)

        b_transitions = list(kripke.IterBTransitions(node))
        in_disj[node] = z3.Or(*[
            to_z3(XMLUtils.CreateTransition(p, node, flag)) for p, flag in b_transitions
        ]) if b_transitions else z3.BoolVal(False)
    return out_disj, in_disj


def rotated_all_pairs(nodes):
    """Full n*(n-1) all-pairs set (source != dest), stride-permuted so
    consecutive queries essentially never share source or destination --
    the worst case for incremental locality, matching axis5's own
    methodology."""
    pairs = [(s, d) for s in nodes for d in nodes if s != d]
    n_pairs = len(pairs)
    stride = max(2, n_pairs // 3)
    while math.gcd(stride, n_pairs) != 1:
        stride += 1
    return [pairs[(j * stride) % n_pairs] for j in range(n_pairs)]


def run_ad6_sample(kripke, encoding, pairs):
    t0 = time.perf_counter()
    results = []
    for source, dest in pairs:
        instance = Instantiator.InstantiateEndToEnd(kripke, deepcopy(encoding), source, dest)
        results.append(bool(PycoSATAdapter().Solve(instance)))
    return time.perf_counter() - t0, results


def run_z3_fresh_sample(base_z3, assumptions):
    t0 = time.perf_counter()
    for assumption in assumptions:
        solver = z3.Solver()
        solver.add(base_z3)
        solver.check(assumption)
    return time.perf_counter() - t0


def run_z3_incremental_full(base_z3, assumptions):
    t0 = time.perf_counter()
    solver = z3.Solver()
    solver.add(base_z3)
    results = []
    for assumption in assumptions:
        results.append(str(solver.check(assumption)) == 'sat')
    return time.perf_counter() - t0, results


if __name__ == '__main__':
    base_size = 140

    print("building base (n=%d rules)..." % base_size)
    kripke, encoding = build_model(base_size)
    nodes = query_node_keys(kripke, base_size)[:N]

    kripke2, base_xml = _capture_base_formula(base_size)
    nodes2 = query_node_keys(kripke2, base_size)[:N]
    root = base_xml[0] if base_xml.tag == XMLUtils.FORMULA else base_xml
    base_z3 = to_z3(root)

    all_pairs = rotated_all_pairs(nodes)
    all_pairs2 = rotated_all_pairs(nodes2)
    print("n=%d nodes, %d full all-pairs (source != dest)" % (N, len(all_pairs)))

    print("\nprecomputing per-node disjunctions once (2*n conversions)...")
    t0 = time.perf_counter()
    out_disj, in_disj = precompute_disjunctions(kripke2, nodes2)
    prep_time = time.perf_counter() - t0
    print("prep time: %.4fs" % prep_time)

    print("\n-- sample-based rate for ad6-real and Z3-fresh (extrapolated to full matrix) --")
    sample_size = 300
    sample_pairs = all_pairs[:sample_size]
    sample_pairs2 = all_pairs2[:sample_size]

    ad6_sample_time, ad6_sample_results = run_ad6_sample(kripke, encoding, sample_pairs)
    ad6_rate = ad6_sample_time / sample_size
    print("ad6-real:  %d-pair sample=%.4fs  rate=%.5fs/pair  "
          "EXTRAPOLATED full (%d pairs)=%.1fs (%.1f min)"
          % (sample_size, ad6_sample_time, ad6_rate, len(all_pairs),
             ad6_rate * len(all_pairs), ad6_rate * len(all_pairs) / 60))

    sample_assumptions = [z3.And(out_disj[s], in_disj[d]) for s, d in sample_pairs2]
    z3_fresh_sample_time = run_z3_fresh_sample(base_z3, sample_assumptions)
    z3_fresh_rate = z3_fresh_sample_time / sample_size
    print("Z3-fresh:  %d-pair sample=%.4fs  rate=%.5fs/pair  "
          "EXTRAPOLATED full (%d pairs)=%.1fs (%.1f min)"
          % (sample_size, z3_fresh_sample_time, z3_fresh_rate, len(all_pairs),
             z3_fresh_rate * len(all_pairs), z3_fresh_rate * len(all_pairs) / 60))

    print("\n-- Z3 incremental: ACTUALLY RUN at the full %d-pair matrix --" % len(all_pairs))
    t0 = time.perf_counter()
    full_assumptions = [z3.And(out_disj[s], in_disj[d]) for s, d in all_pairs2]
    build_assumptions_time = time.perf_counter() - t0
    print("(building all %d assumption terms took %.4fs)"
          % (len(full_assumptions), build_assumptions_time))

    z3_incr_time, z3_incr_results = run_z3_incremental_full(base_z3, full_assumptions)
    print("Z3-incremental FULL RUN: %.4fs (%.2f min) for %d pairs -- %.6fs/pair average"
          % (z3_incr_time, z3_incr_time / 60, len(all_pairs),
             z3_incr_time / len(all_pairs)))

    print("\n-- correctness check on the sample --")
    incr_sample_results = z3_incr_results[:sample_size]
    match = ad6_sample_results == incr_sample_results
    print("ad6-real vs Z3-incremental agree on first %d (of the full-matrix run's) pairs: %s"
          % (sample_size, match))

    print("\n-- summary --")
    print("ad6-real   (extrapolated): %10.1fs (%.1f min)"
          % (ad6_rate * len(all_pairs), ad6_rate * len(all_pairs) / 60))
    print("Z3-fresh   (extrapolated): %10.1fs (%.1f min)"
          % (z3_fresh_rate * len(all_pairs), z3_fresh_rate * len(all_pairs) / 60))
    print("Z3-incremental (MEASURED): %10.4fs (%.2f min)"
          % (z3_incr_time, z3_incr_time / 60))
