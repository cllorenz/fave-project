"""Axis 5 -- follow-up to Axis 4's open gap (AD6_ENCODING_PLAN.md §3.4):
does incremental/assumption-based solving still amortize when the QUERY's
SOURCE varies too, not just the destination -- the genuine n-by-n
all-pairs shape FaVe's real cross-family comparisons actually use
(AD6_PLAN.md §1.2's InstantiateEndToEnd primitive), not Axis 4's
single-fixed-source-many-destinations simplification.

Uses ad6's real InstantiateEndToEnd(Source, Destination) -- the actual
FaVe-integration primitive, not InstantiateReach's init-only reachability
-- so BOTH a DisjSrc (source's own outgoing edge fired) and a DisjDst
(destination's own incoming edge fired) assumption vary per query.

Also tests whether QUERY ORDER matters for how much incremental benefit
you get: grouped-by-source (many destinations against a momentarily-fixed
source, then move to the next source) vs. fully rotated (source AND
destination both change every single query) -- a directly actionable
scheduling question if incremental solving is ever adopted for real.

Usage: PYTHONPATH=../ad6 python3 axis5_cross_source.py
"""
import sys
import os
import time
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

import z3

from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter
from src.xml.xmlutils import XMLUtils

from axis4_incremental import build_model, query_node_keys, _capture_base_formula
from xml_to_z3 import to_z3


def end_to_end_assumption(kripke, source, destination):
    """Mirrors Instantiator.InstantiateEndToEnd's own two disjuncts
    exactly (src's own outgoing edge fired; dst's own incoming edge
    fired), built directly as a Z3 formula instead of appended XML."""
    f_transitions = list(kripke.IterFTransitions(source))
    disj_src = z3.Or(*[
        to_z3(XMLUtils.CreateTransition(source, t, flag)) for t, flag in f_transitions
    ]) if f_transitions else z3.BoolVal(False)

    b_transitions = list(kripke.IterBTransitions(destination))
    disj_dst = z3.Or(*[
        to_z3(XMLUtils.CreateTransition(p, destination, flag)) for p, flag in b_transitions
    ]) if b_transitions else z3.BoolVal(False)

    return z3.And(disj_src, disj_dst)


def run_ad6_fresh(kripke, encoding, pairs):
    t0 = time.perf_counter()
    results = []
    for source, dest in pairs:
        instance = Instantiator.InstantiateEndToEnd(kripke, deepcopy(encoding), source, dest)
        results.append(bool(PycoSATAdapter().Solve(instance)))
    return time.perf_counter() - t0, results


def run_z3_fresh(base_z3, assumptions):
    t0 = time.perf_counter()
    for assumption in assumptions:
        solver = z3.Solver()
        solver.add(base_z3)
        solver.check(assumption)
    return time.perf_counter() - t0


def run_z3_incremental(base_z3, assumptions):
    t0 = time.perf_counter()
    solver = z3.Solver()
    solver.add(base_z3)
    results = []
    for assumption in assumptions:
        results.append(str(solver.check(assumption)) == 'sat')
    return time.perf_counter() - t0, results


def grouped_by_source_order(nodes_k):
    return [(s, d) for s in nodes_k for d in nodes_k if s != d]


def fully_rotated_order(nodes_k):
    """Same pair SET as grouped_by_source_order, different VISITATION
    ORDER: a stride-based permutation (stride coprime with the pair
    count) so consecutive queries essentially never share source OR
    destination -- the opposite extreme from grouped_by_source_order's
    "same source, K-1 destinations in a row"."""
    import math
    pairs = grouped_by_source_order(nodes_k)
    n = len(pairs)
    stride = max(2, n // 3)
    while math.gcd(stride, n) != 1:
        stride += 1
    return [pairs[(j * stride) % n] for j in range(n)]


if __name__ == '__main__':
    base_size = 150
    k = 15  # K*(K-1) = 210 (source, dest) pairs, source != dest, both varying

    kripke, encoding = build_model(base_size)
    nodes_k = query_node_keys(kripke, base_size)[:k]

    kripke2, base_xml = _capture_base_formula(base_size)
    nodes2_k = query_node_keys(kripke2, base_size)[:k]
    root = base_xml[0] if base_xml.tag == XMLUtils.FORMULA else base_xml
    base_z3 = to_z3(root)

    print("-- correctness check (grouped-by-source order, ad6 real vs. Z3 incremental) --")
    grouped_pairs = grouped_by_source_order(nodes_k)
    grouped_pairs2 = grouped_by_source_order(nodes2_k)
    ad6_time, ad6_results = run_ad6_fresh(kripke, encoding, grouped_pairs)
    assumptions_grouped = [end_to_end_assumption(kripke2, s, d) for s, d in grouped_pairs2]
    z3incr_time, z3_results = run_z3_incremental(base_z3, assumptions_grouped)
    print("pairs=%d  match=%s  ad6=%.4fs  z3_incremental=%.4fs"
          % (len(grouped_pairs), ad6_results == z3_results, ad6_time, z3incr_time))

    print("\n-- does query ORDER change incremental benefit? (same %d pairs, two orders) --"
          % len(grouped_pairs))
    z3_fresh_grouped = run_z3_fresh(base_z3, assumptions_grouped)
    print("grouped-by-source:  z3_fresh=%.4fs  z3_incremental=%.4fs"
          % (z3_fresh_grouped, z3incr_time))

    rotated_pairs2 = fully_rotated_order(nodes2_k)
    assumptions_rotated = [end_to_end_assumption(kripke2, s, d) for s, d in rotated_pairs2]
    z3_fresh_rotated = run_z3_fresh(base_z3, assumptions_rotated)
    z3_incr_rotated, _ = run_z3_incremental(base_z3, assumptions_rotated)
    print("fully-rotated:      z3_fresh=%.4fs  z3_incremental=%.4fs"
          % (z3_fresh_rotated, z3_incr_rotated))

    print("\n-- scaling: does cross-source incremental reuse still beat fresh solving as "
          "pair count grows? --")
    for subset_k in (5, 8, 11, 15):
        sub_nodes = nodes2_k[:subset_k]
        pairs = fully_rotated_order(sub_nodes)
        assumptions = [end_to_end_assumption(kripke2, s, d) for s, d in pairs]
        ad6_sub_time, _ = run_ad6_fresh(kripke, encoding, fully_rotated_order(nodes_k[:subset_k]))
        z3f = run_z3_fresh(base_z3, assumptions)
        z3i, _ = run_z3_incremental(base_z3, assumptions)
        print("pairs=%4d  ad6_fresh=%.4fs  z3_fresh=%.4fs  z3_incremental=%.4fs"
              % (len(pairs), ad6_sub_time, z3f, z3i))
