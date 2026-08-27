"""Axis 7 -- the last open item on the incremental-solving lever
(AD6_ENCODING_PLAN.md §3.4-3.8): does the SAME amortization show up using
ad6's OWN solver family's native incremental API, not just Z3's?

ad6's actual adapters (MiniSATAdapter/ClaspAdapter) shell out to the
`minisat`/`clasp` CLI binaries -- a fresh process, fresh DIMACS file, no
state carried between calls, by construction. That is NOT what "minisat's
native incremental API" means -- MiniSat's real incremental interface
(`Solver::solve(assumptions)`) is a C++ library call, invisible to a CLI
invocation. PySAT (`pysat.solvers.Minisat22`) wraps that same underlying
MiniSat engine as a genuine incremental library call (add_clause any
time, solve(assumptions=[...]) reusing internal state) -- the fair way to
test "minisat itself," not "the CLI wrapper ad6 happens to use."

Since PySAT's assumptions must be single literals (not arbitrary
formulas, unlike Z3's check()), a query's DISJUNCTION (source's own
outgoing edges; destination's own incoming edges) needs one Tseitin OR-
gate auxiliary variable each -- built directly against ad6's own DIMACS
variable numbering (AbstractSolver._ConvertToDIMACS, the same method
MiniSATAdapter/ClaspAdapter already use to talk to their CLI binaries),
so this is genuinely "ad6's own encoding, solved incrementally," not a
different formula representation like Z3's arbitrary-Boolean-term model.

Tested against the REAL wl_up model + REAL bench/wl_up/cchecks.json
queries (same as axis6_wlup_real.py) -- the most valuable, most credible
version of this question, not a synthetic proxy.

Usage: python3 axis7_native_incremental.py [sample_size]
(run from ad6_encoding_bench/)
"""
import sys
import os
import time
from copy import deepcopy

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from axis6_wlup_real import (
    build_real_wlup, instantiate_real_model, load_cchecks_as_queries, AD6_ROOT, FAVE_ROOT,
)
from axis6b_wlup_full_scale import load_all_cchecks_as_queries

sys.path.insert(0, AD6_ROOT)
from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter
from src.solver.minisat import MiniSATAdapter
from src.xml.xmlutils import XMLUtils
from src.parser import favemodel
import fave_bridge

from pysat.solvers import Minisat22


class DimacsBridge:
    """Stable name<->DIMACS-index mapping seeded from ad6's own base
    encoding (via AbstractSolver._ConvertToDIMACS, the exact method
    MiniSATAdapter/ClaspAdapter already use), extendable for query-time
    literals that don't already appear in the base."""

    def __init__(self, base_encoding):
        adapter = MiniSATAdapter()
        variables, dimacs_clauses = adapter._ConvertToDIMACS(base_encoding)
        self.name_to_index = {name: i + 1 for i, name in enumerate(variables)}
        self.next_index = len(variables) + 1
        self.base_clauses = dimacs_clauses

    def index_for(self, name):
        if name not in self.name_to_index:
            self.name_to_index[name] = self.next_index
            self.next_index += 1
        return self.name_to_index[name]

    def literal(self, xml_var):
        idx = self.index_for(xml_var.attrib[XMLUtils.ATTRNAME])
        return -idx if xml_var.attrib.get(XMLUtils.ATTRNEGATED) == 'true' else idx

    def or_gate(self, xml_vars):
        """Returns (literal, extra_clauses). 0 vars -> False (UNSAT
        literal via a fresh always-false aux var); 1 var -> that literal
        directly, no gate needed; >1 -> a fresh Tseitin OR-gate aux var."""
        lits = [self.literal(v) for v in xml_vars]
        if not lits:
            aux = self.next_index
            self.next_index += 1
            return aux, [[-aux]]  # force aux false -- "no incoming/outgoing edge" is UNSAT
        if len(lits) == 1:
            return lits[0], []
        aux = self.next_index
        self.next_index += 1
        clauses = [[-l, aux] for l in lits] + [[-aux] + lits]
        return aux, clauses


def query_gate(bridge, kripke, favemodel_mod, fave_bridge_mod, ir, q):
    """Returns (assumption_literals, extra_clauses) for one query -- the
    ad6-DIMACS-native equivalent of axis6's Z3 assumption formula."""
    source = favemodel_mod.gen_entry_key(q['source'])
    destination = favemodel_mod.query_destination_key(q['probe'], ir)

    f_trans = [XMLUtils.CreateTransition(source, t, flag)
               for t, flag in kripke.IterFTransitions(source)]
    b_trans = [XMLUtils.CreateTransition(p, destination, flag)
               for p, flag in kripke.IterBTransitions(destination)]

    src_lit, src_clauses = bridge.or_gate(f_trans)
    dst_lit, dst_clauses = bridge.or_gate(b_trans)

    assumptions = [src_lit, dst_lit]
    extra_clauses = src_clauses + dst_clauses

    if q.get('src_cidr') and favemodel_mod._is_constrained(q['src_cidr']):
        for lit in fave_bridge_mod._seed_literals(q['src_cidr']):
            assumptions.append(bridge.literal(lit))
    for lit in fave_bridge_mod._state_literals(q.get('cond')):
        assumptions.append(bridge.literal(lit))

    return assumptions, extra_clauses


if __name__ == '__main__':
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    half = sample_size // 2

    print("building real wl_up FaVe model...")
    engine, ir = build_real_wlup()
    print("generators=%d probes=%d devices=%d" %
          (len(engine._generators), len(engine._probes), len(ir['devices'])))

    print("\ninstantiating real ad6 Kripke/CNF model...")
    t0 = time.perf_counter()
    kripke, encoding = instantiate_real_model(ir)
    print("build time: %.2fs, %d Kripke nodes" %
          (time.perf_counter() - t0, len(list(kripke.IterNodes()))))

    plain_qs, stateful_qs = load_cchecks_as_queries(engine, half, half)
    queries = plain_qs + stateful_qs
    print("sample: %d queries (%d stateful)" % (len(queries), len(stateful_qs)))

    print("\n-- ad6 real (Instantiator.SolveAcyclicEndToEnd, actual production path) --")
    solver = PycoSATAdapter()
    acyclic_cache = {}
    ad6_results = []
    t0 = time.perf_counter()
    for q in queries:
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, deepcopy(encoding), source, destination)
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            instance[0].extend(fave_bridge._seed_literals(q['src_cidr']))
        for literal in fave_bridge._state_literals(q.get('cond')):
            instance[0].append(literal)
        reachable = Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, source, destination, Cache=acyclic_cache)
        ad6_results.append(bool(reachable))
    ad6_time = time.perf_counter() - t0
    print("ad6 real: %d queries in %.2fs (%.4fs/query)" %
          (len(queries), ad6_time, ad6_time / len(queries)))

    print("\nbuilding DIMACS bridge from the same base encoding...")
    t0 = time.perf_counter()
    bridge_master = DimacsBridge(encoding)
    print("base: %d vars, %d clauses (%.2fs)" %
          (bridge_master.next_index - 1, len(bridge_master.base_clauses), time.perf_counter() - t0))

    print("\nbuilding per-query gates (assumptions + extra clauses)...")
    t0 = time.perf_counter()
    query_gates = [query_gate(bridge_master, kripke, favemodel, fave_bridge, ir, q)
                   for q in queries]
    print("built in %.2fs" % (time.perf_counter() - t0))

    print("\n-- PySAT/Minisat22 FRESH (new solver + full base + this query's gate, per query) --")
    t0 = time.perf_counter()
    fresh_results = []
    for assumptions, extra_clauses in query_gates:
        s = Minisat22(bootstrap_with=bridge_master.base_clauses)
        for c in extra_clauses:
            s.add_clause(c)
        fresh_results.append(s.solve(assumptions=assumptions))
        s.delete()
    fresh_time = time.perf_counter() - t0
    print("PySAT fresh: %d queries in %.4fs (%.5fs/query)" %
          (len(queries), fresh_time, fresh_time / len(queries)))

    print("\n-- PySAT/Minisat22 INCREMENTAL (one persistent solver, native assumptions) --")
    t0 = time.perf_counter()
    s_incr = Minisat22(bootstrap_with=bridge_master.base_clauses)
    incr_results = []
    for assumptions, extra_clauses in query_gates:
        for c in extra_clauses:
            s_incr.add_clause(c)
        incr_results.append(s_incr.solve(assumptions=assumptions))
    incr_time = time.perf_counter() - t0
    s_incr.delete()
    print("PySAT incremental: %d queries in %.4fs (%.5fs/query)" %
          (len(queries), incr_time, incr_time / len(queries)))

    print("\n-- correctness --")
    print("ad6 real vs PySAT fresh:       match =", ad6_results == fresh_results)
    print("ad6 real vs PySAT incremental: match =", ad6_results == incr_results)

    print("\n-- SUMMARY (n=%d, %d stateful) --" % (len(queries), len(stateful_qs)))
    print("ad6 real (CLI subprocess, current architecture): %8.3fs  (%.5fs/query)"
          % (ad6_time, ad6_time / len(queries)))
    print("PySAT/Minisat22 fresh (native lib, no reuse):     %8.3fs  (%.5fs/query)"
          % (fresh_time, fresh_time / len(queries)))
    print("PySAT/Minisat22 incremental (native, reused):     %8.3fs  (%.5fs/query)"
          % (incr_time, incr_time / len(queries)))

    print("\n-- PySAT/Minisat22 incremental: ACTUALLY RUN on the FULL real query set --")
    all_queries = load_all_cchecks_as_queries(engine)
    print("full set: %d queries" % len(all_queries))
    t0 = time.perf_counter()
    bridge_full = DimacsBridge(encoding)
    all_gates = [query_gate(bridge_full, kripke, favemodel, fave_bridge, ir, q)
                 for q in all_queries]
    print("built all gates in %.2fs" % (time.perf_counter() - t0))

    t0 = time.perf_counter()
    s_full = Minisat22(bootstrap_with=bridge_full.base_clauses)
    full_results = []
    for assumptions, extra_clauses in all_gates:
        for c in extra_clauses:
            s_full.add_clause(c)
        full_results.append(s_full.solve(assumptions=assumptions))
    full_time = time.perf_counter() - t0
    s_full.delete()
    print("PySAT incremental FULL RUN: %d queries in %.2fs (%.1f min) -- %.6fs/query average"
          % (len(all_queries), full_time, full_time / 60, full_time / len(all_queries)))

    print("\nEXTRAPOLATED ad6-real for full %d: %.1fs (%.2f hr)"
          % (len(all_queries), (ad6_time / len(queries)) * len(all_queries),
             (ad6_time / len(queries)) * len(all_queries) / 3600))
