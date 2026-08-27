"""Axis 8, PySAT retry (2026-08-27): axis8b's Z3-based attempt never
finished even ONE solver.check() in 90 minutes on Stanford's real
rank-constrained base (443,963 extra clauses) -- neither fresh nor
incremental. That implicated Z3's *term-based* construction specifically:
the Z3 base was built from the PRE-CNF nested formula (captured via
monkeypatching SATUtils.ConvertToCNF, matching axis6's own Z3-comparison
convention) -- Z3 then has to internally Tseitin-transform + reason over
a huge nested implication/equality tree from scratch. ad6's own solver
(pycosat) meanwhile DID solve the same logical content, just slowly
(2164.64s/2259.70s per escalated query in axis8's first successful run --
via SolveAcyclicEndToEnd's CEGAR loop, which pays for a FULL Python-level
DIMACS reconversion of the ~515k-clause instance on EVERY iteration, not
just once).

This version stays entirely within ad6's own already-CNF'd representation
(favemodel.instantiate_base's `encoding`, exactly what fave_bridge.py
uses in production) plus the already-CNF'd _CreateAcyclicConstraints
output (both flat clause-level XML, not nested formulas) -- converts them
ONCE to DIMACS ints (AbstractSolver._ConvertToDIMACS, the same method
MiniSATAdapter/ClaspAdapter use), and drives PySAT's Minisat22 (the same
solver FAMILY axis7 already confirmed gives the ~490x win on wl_up) via
its real native incremental API. This is the apples-to-apples version of
the experiment: same encoding ad6 itself already uses and already proved
tractable (pycosat solved it), same solver family, just without paying
for CEGAR's repeated from-scratch Python-level reconversion.

No CEGAR needed: _CreateAcyclicConstraints's rank encoding is sound by
construction via a plain solve (see its own docstring / B1's writeup) --
baking it into the base ONCE and doing a single solver.solve(assumptions)
per query should be a complete, correct answer, not just a fast path.

Usage: python3 -u axis8c_stanford_pysat.py [n_queries]
(no special ulimit needed -- doesn't touch the codepath that segfaulted
in axis8's first attempt, but running with `ulimit -s unlimited` first is
cheap insurance since _CreateAcyclicConstraints is still built here)
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

# From axis8_stanford_incremental.py's first successful (unlimited-stack)
# run, in exact query order (queries = [{"source": s, "probe": p} for p in
# probes for s in sources], both sorted -- deterministic, same order this
# script builds).
KNOWN_AD6_REAL = [True, False, False, True, True]


def build_real_stanford():
    sys.path.insert(0, FAVE_ROOT)
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("axis8c_stanford")
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


class DimacsBridge:
    """Same design as axis7_native_incremental.py's DimacsBridge -- stable
    name<->DIMACS-index mapping seeded from ad6's own base encoding."""

    def __init__(self, base_encoding, MiniSATAdapter, XMLUtils):
        self._XMLUtils = XMLUtils
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
        idx = self.index_for(xml_var.attrib[self._XMLUtils.ATTRNAME])
        return -idx if xml_var.attrib.get(self._XMLUtils.ATTRNEGATED) == 'true' else idx

    def or_gate(self, xml_vars):
        lits = [self.literal(v) for v in xml_vars]
        if not lits:
            aux = self.next_index
            self.next_index += 1
            return aux, [[-aux]]
        if len(lits) == 1:
            return lits[0], []
        aux = self.next_index
        self.next_index += 1
        clauses = [[-l, aux] for l in lits] + [[-aux] + lits]
        return aux, clauses


if __name__ == '__main__':
    n_queries = int(sys.argv[1]) if len(sys.argv) > 1 else 256

    print("building real wl_stanford FaVe model (Ad6Adapter + InProcessFaVe)...", flush=True)
    t0 = time.perf_counter()
    engine, ir, sources, probes = build_real_stanford()
    print("build_real_stanford: %.2fs, sources=%d probes=%d devices=%d" %
          (time.perf_counter() - t0, len(sources), len(probes), len(ir['devices'])), flush=True)

    print("\ninstantiating real ad6 Kripke/CNF model (favemodel.instantiate_base -- the production path)...", flush=True)
    t0 = time.perf_counter()
    kripke, encoding = instantiate_real_model(ir)
    print("build time: %.2fs, %d Kripke nodes" %
          (time.perf_counter() - t0, len(list(kripke.IterNodes()))), flush=True)

    sys.path.insert(0, AD6_ROOT)
    from src.parser import favemodel
    from src.core.instantiator import Instantiator
    from src.solver.minisat import MiniSATAdapter
    from src.xml.xmlutils import XMLUtils
    from pysat.solvers import Minisat22

    print("\nbuilding SCC-scoped acyclic rank constraints ONCE (Instantiator._CreateAcyclicConstraints)...", flush=True)
    t0 = time.perf_counter()
    acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
    print("rank-constraint build: %.2fs, %d extra clauses (already CNF'd, same as ad6's own escalation path)" %
          (time.perf_counter() - t0, len(acyclic_constraints)), flush=True)

    print("\nbaking rank constraints into a copy of the base encoding...", flush=True)
    combined = deepcopy(encoding)
    combined[0].extend(deepcopy(acyclic_constraints))

    print("converting combined base (data-plane + rank constraints) -> DIMACS ONCE...", flush=True)
    t0 = time.perf_counter()
    bridge = DimacsBridge(combined, MiniSATAdapter, XMLUtils)
    print("DIMACS conversion: %.2fs -- %d vars, %d clauses" %
          (time.perf_counter() - t0, bridge.next_index - 1, len(bridge.base_clauses)), flush=True)

    queries = [{"source": s, "probe": p} for p in probes for s in sources]
    print("\n%d total (source, probe) pairs; running %d" % (len(queries), min(n_queries, len(queries))), flush=True)

    def query_gate(q):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        f_trans = [XMLUtils.CreateTransition(source, t, flag)
                   for t, flag in kripke.IterFTransitions(source)]
        b_trans = [XMLUtils.CreateTransition(p, destination, flag)
                   for p, flag in kripke.IterBTransitions(destination)]
        src_lit, src_clauses = bridge.or_gate(f_trans)
        dst_lit, dst_clauses = bridge.or_gate(b_trans)
        return [src_lit, dst_lit], src_clauses + dst_clauses

    print("\nloading base+rank clauses into a PERSISTENT Minisat22 instance (built ONCE)...", flush=True)
    t0 = time.perf_counter()
    solver = Minisat22(bootstrap_with=bridge.base_clauses)
    load_time = time.perf_counter() - t0
    print("persistent solver load: %.2fs" % load_time, flush=True)

    n = min(n_queries, len(queries))
    print("\n-- PySAT/Minisat22 INCREMENTAL (one persistent solver, base+rank built ONCE) -- THE KEY NUMBER --", flush=True)
    results = []
    t0 = time.perf_counter()
    for i, q in enumerate(queries[:n], start=1):
        assumptions, extra_clauses = query_gate(q)
        for c in extra_clauses:
            solver.add_clause(c)
        sat = solver.solve(assumptions=assumptions)
        results.append(bool(sat))
        if i <= 10 or i % 20 == 0 or i == n:
            elapsed = time.perf_counter() - t0
            print("  [%d/%d] %s -> %s: reachable=%s  (elapsed %.3fs, %.5fs/query so far)" %
                  (i, n, q['source'], q['probe'], sat, elapsed, elapsed / i), flush=True)
    total_time = time.perf_counter() - t0
    print("PySAT incremental: %d queries in %.4fs (%.5fs/query)" %
          (n, total_time, total_time / n), flush=True)

    print("\n-- correctness: known ad6-real (5 queries, from the prior run) vs PySAT incremental (same order) --", flush=True)
    n_check = min(5, n)
    mismatches = [(i, KNOWN_AD6_REAL[i], results[i]) for i in range(n_check) if KNOWN_AD6_REAL[i] != results[i]]
    print("compared %d pairs, %d mismatches" % (n_check, len(mismatches)), flush=True)
    for m in mismatches:
        print("  MISMATCH:", queries[m[0]], m, flush=True)

    print("\n-- SUMMARY --", flush=True)
    print("known ad6-real (prior run):     5 queries, 2 escalated at 2164.64s/2259.70s, 3 fast-path <1s", flush=True)
    print("DIMACS base+rank one-time build: %.2fs" % load_time, flush=True)
    print("PySAT incremental:               %8.3fs over %d queries (%.5fs/query)" %
          (total_time, n, total_time / n), flush=True)
    if n == len(queries):
        extrapolated_ad6 = (2164.64 + 2259.70) / 2 * 0.54 * n + 0.5 * 0.46 * n
        print("PySAT incremental covers ALL %d real Stanford source->probe pairs." % len(queries), flush=True)
        print("(rough sanity extrapolation of ad6-real at B1's 54%% escalation rate, ~avg observed "
              "escalated cost: ~%.0fs / ~%.2fhr -- illustrative only, not a rerun)" %
              (extrapolated_ad6, extrapolated_ad6 / 3600.0), flush=True)
