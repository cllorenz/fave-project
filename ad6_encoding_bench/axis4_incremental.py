"""Axis 4 -- orthogonal to Axes 0-3 (AD6_ENCODING_PLAN.md §6's lever, Factor
A): does incremental/assumption-based solving amortize ad6's O(n) *query
count* problem the way a domain-specific "one flood answers all
destinations" traversal does? Axes 0-3 were all about Factor B (per-query
build/encode cost, holding query count fixed); this is about what happens
as the number of *queries against the same shared base* grows.

ad6's real architecture today (fave_bridge.py's query loop, mirrored
exactly by run_ad6_fresh below): build the shared base ONCE, then for each
query, deepcopy the base + append that query's own disjunction + solve
FROM SCRATCH -- no state (propagated units, learned clauses) carries
between queries, even though most of the formula is identical each time.

Three encodings of the SAME "N independent reachability queries against
one shared base" problem:
1. run_ad6_fresh -- ad6's real, current architecture (PycoSATAdapter, one
   fresh Solve() per query).
2. run_z3_fresh -- SAME base formula (captured pre-CNF, converted to Z3 via
   xml_to_z3.py), but a BRAND NEW z3.Solver() per query -- controls for
   "is Z3 just a faster engine" (Axis 0/2's question), isolating whether
   incrementality *itself*, not solver choice, is what would matter here.
3. run_z3_incremental -- ONE persistent z3.Solver(), the base added once,
   then N `solver.check(assumption)` calls -- genuine incremental/
   assumption-based solving, reusing internal state across queries.

If (3) scales flatter than (1)/(2) as N grows, that is the Factor-A signal
AD6_PLAN.md §6 predicted. If (3) ~ (2), incrementality itself isn't doing
anything here (independent of engine choice) -- a valid negative result,
same spirit as axis3b's.

Usage: PYTHONPATH=../ad6 python3 axis4_incremental.py
"""
import sys
import os
import time
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

import z3

from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser
from src.core.instantiator import Instantiator
from src.sat.satutils import SATUtils
from src.solver.pycosat import PycoSATAdapter
from src.xml.xmlutils import XMLUtils

from xml_to_z3 import to_z3

FW_NAME = 'axis4'
_ORIGINAL_CONVERT = SATUtils.ConvertToCNF


def build_chain_ruleset(n_queries):
    """A single router, n_queries sequential rules -- distinct conditions,
    doesn't matter semantically, each rule's own key is a distinct,
    addressable node ad6 already supports querying (InstantiateReach's
    real, existing per-node mode, AD6_PLAN.md §1.2's own table)."""
    lines = ['ip6tables -P ROUTER1 DROP']
    for i in range(n_queries):
        lines.append('ip6tables -A ROUTER1 -d 2001:db8:9:%x::/64 -j DROP' % i)
    return '\n'.join(lines) + '\n'


def build_model(n_queries):
    ruleset = build_chain_ruleset(n_queries)
    fw = IP6TablesParser.parse(ruleset, FW_NAME)
    config = GenUtils.config()
    firewalls = GenUtils.firewalls()
    firewalls.append(fw)
    config.append(firewalls)
    kripke, encoding = Instantiator.InstantiateBase(
        config, Inits=['%s_router1_r0' % FW_NAME], default_inits=False)
    return kripke, encoding


def query_node_keys(kripke, n_queries):
    # every rule's own key, in the order IP6TablesParser assigned them
    return sorted(
        (n for n in kripke.IterNodes() if n.startswith('%s_router1_r' % FW_NAME)),
        key=lambda n: int(n.rsplit('r', 1)[1]),
    )[:n_queries]


def run_ad6_fresh(kripke, encoding, nodes):
    t0 = time.perf_counter()
    for node in nodes:
        instance = Instantiator.InstantiateReach(kripke, deepcopy(encoding), node)
        PycoSATAdapter().Solve(instance)
    return time.perf_counter() - t0


def _capture_base_formula(n_queries):
    """Same monkeypatch trick as axis1_tseitin.py -- capture the LAST
    (outermost, InstantiateBase-level) pre-CNF formula, which by then
    contains the whole model's propositional content (per-edge parts
    were already individually flattened by earlier, inner calls)."""
    captured = []

    def _capturing(Formula):
        captured.append(deepcopy(Formula))
        _ORIGINAL_CONVERT(Formula)

    SATUtils.ConvertToCNF = staticmethod(_capturing)
    try:
        kripke, encoding = build_model(n_queries)
    finally:
        SATUtils.ConvertToCNF = _ORIGINAL_CONVERT
    return kripke, captured[-1]


def _prepare_z3(kripke, base_formula_xml, nodes):
    """Conversion (XML -> Z3 term, and building each query's assumption
    formula) happens ONCE, untimed, identically for both baselines below --
    so the timed region isolates JUST the solver-state-reuse question, not
    Python-level formula-construction cost (that's Axis 1's question, not
    this one)."""
    root = base_formula_xml[0] if base_formula_xml.tag == XMLUtils.FORMULA else base_formula_xml
    base_z3 = to_z3(root)
    assumptions = []
    for node in nodes:
        if XMLUtils.INIT in kripke.GetNode(node).Props:
            assumptions.append(z3.BoolVal(True))
        else:
            assumptions.append(z3.Or(*[
                to_z3(XMLUtils.CreateTransition(pred, node, flag))
                for pred, flag in kripke.IterBTransitions(node)
            ]))
    return base_z3, assumptions


def run_z3_fresh(base_z3, assumptions):
    """A brand-new Solver + re-`add()` of the (already-converted) base
    formula per query -- no learned-clause/propagation state carries over.
    Isolates "no incremental reuse", holding formula-construction cost and
    solver engine fixed."""
    t0 = time.perf_counter()
    for assumption in assumptions:
        solver = z3.Solver()
        solver.add(base_z3)
        solver.check(assumption)
    return time.perf_counter() - t0


def run_z3_incremental(base_z3, assumptions):
    """ONE persistent Solver, base added once, N assumption-based checks --
    genuine incremental solving."""
    t0 = time.perf_counter()
    solver = z3.Solver()
    solver.add(base_z3)
    for assumption in assumptions:
        solver.check(assumption)
    return time.perf_counter() - t0


def scaling_with_base(sizes=(10, 50, 100, 300)):
    """Base size == query count, grown together (realistic, but conflates
    Factor A -- query count -- with Factor B -- base/rule count)."""
    print("-- base size scales WITH query count (realistic, but conflates Factor A/B) --")
    for n in sizes:
        kripke, encoding = build_model(n)
        nodes = query_node_keys(kripke, n)
        ad6_time = run_ad6_fresh(kripke, encoding, nodes)

        kripke2, base_xml = _capture_base_formula(n)
        nodes2 = query_node_keys(kripke2, n)
        base_z3, assumptions = _prepare_z3(kripke2, base_xml, nodes2)
        z3_fresh_time = run_z3_fresh(base_z3, assumptions)
        z3_incr_time = run_z3_incremental(base_z3, assumptions)

        print("n=%4d  ad6_fresh=%.4fs  z3_fresh=%.4fs  z3_incremental=%.4fs"
              % (n, ad6_time, z3_fresh_time, z3_incr_time))


def scaling_isolated_factor_a(base_size=200, query_counts=(10, 25, 50, 100, 200)):
    """Base topology FIXED at base_size; only the NUMBER OF QUERIES against
    it varies (a subset of the same node set each time) -- isolates Factor
    A cleanly, holding Factor B (base build cost) constant."""
    print("\n-- base size FIXED at %d, only query count varies (isolates Factor A) --"
          % base_size)
    kripke, encoding = build_model(base_size)
    all_nodes = query_node_keys(kripke, base_size)

    kripke2, base_xml = _capture_base_formula(base_size)
    all_nodes2 = query_node_keys(kripke2, base_size)
    base_z3, all_assumptions = _prepare_z3(kripke2, base_xml, all_nodes2)

    for k in query_counts:
        nodes = all_nodes[:k]
        assumptions = all_assumptions[:k]

        ad6_time = run_ad6_fresh(kripke, encoding, nodes)
        z3_fresh_time = run_z3_fresh(base_z3, assumptions)
        z3_incr_time = run_z3_incremental(base_z3, assumptions)

        print("queries=%4d  ad6_fresh=%.4fs  z3_fresh=%.4fs  z3_incremental=%.4fs"
              % (k, ad6_time, z3_fresh_time, z3_incr_time))


if __name__ == '__main__':
    scaling_with_base()
    scaling_isolated_factor_a()
