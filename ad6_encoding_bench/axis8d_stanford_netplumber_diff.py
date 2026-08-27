"""Axis 8, final step (2026-08-27): axis8c_stanford_pysat.py proved the
incremental lever answers all 256 real Stanford source->probe pairs
correctly (vs. ad6-real on the sample) and fast (~16 min). This script
closes the remaining gap flagged in AD6_ENCODING_PLAN.md §3.10: feed
those 256 answers through the SAME oracle-comparison logic
fave/test/test_ad6_wl_stanford.py's own (currently un-runnable-in-
practice) differential test uses -- a live NetPlumber worker, not
reachable.json (the all-to-all POLICY, not the data plane) -- to get a
real answer to "does ad6 (via this architecture) actually match
NetPlumber on the real wl_stanford data plane."

Mirrors test_ad6_wl_stanford.py's setUpClass/test_reachability_matches_
netplumber exactly in spirit -- same oracle, same role-name normalization,
same diff shape -- just computing the 256 reachability answers via the
persistent PySAT/Minisat22 incremental solver instead of
Instantiator.SolveAcyclicEndToEnd's current per-query architecture (which
is what made the real test impractical: 6h/28.9%-complete NO-GO).

Read-only use of ad6/ and fave/'s existing modules -- nothing modified.

Usage: python3 -u axis8d_stanford_netplumber_diff.py
(no special ulimit needed -- doesn't touch the segfault-prone
SolveAcyclicEndToEnd escalation path, and fave_bridge.py's own entry
point is now fixed anyway, see AD6_PLAN.md §5.4 B1's "third item")
"""
import sys
import os
import time
import logging
import tempfile
from copy import deepcopy

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, '..')
FAVE_ROOT = os.path.join(_ROOT, 'fave')
AD6_ROOT = os.path.join(_ROOT, 'ad6')

sys.setrecursionlimit(10 ** 6)

_PREFIX = "bench/wl_stanford/stanford-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def build_real_stanford():
    sys.path.insert(0, FAVE_ROOT)
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("axis8d_stanford")
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
    from src.solver.minisat import MiniSATAdapter
    from src.xml.xmlutils import XMLUtils
    from pysat.solvers import Minisat22

    print("\nbuilding SCC-scoped acyclic rank constraints ONCE...", flush=True)
    t0 = time.perf_counter()
    acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
    print("rank-constraint build: %.2fs, %d extra clauses" %
          (time.perf_counter() - t0, len(acyclic_constraints)), flush=True)

    combined = deepcopy(encoding)
    combined[0].extend(deepcopy(acyclic_constraints))

    print("converting combined base -> DIMACS ONCE...", flush=True)
    t0 = time.perf_counter()
    bridge = DimacsBridge(combined, MiniSATAdapter, XMLUtils)
    print("DIMACS conversion: %.2fs -- %d vars, %d clauses" %
          (time.perf_counter() - t0, bridge.next_index - 1, len(bridge.base_clauses)), flush=True)

    queries = [{"source": s, "probe": p} for p in probes for s in sources]
    print("\n%d total (source, probe) pairs" % len(queries), flush=True)

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

    print("\nloading base+rank clauses into a PERSISTENT Minisat22 instance...", flush=True)
    t0 = time.perf_counter()
    solver = Minisat22(bootstrap_with=bridge.base_clauses)
    print("persistent solver load: %.2fs" % (time.perf_counter() - t0), flush=True)

    print("\n-- solving ALL %d real Stanford pairs via incremental assumptions --" % len(queries), flush=True)
    ad6_reach = {}  # (source_name, probe_name) -> bool
    t0 = time.perf_counter()
    for i, q in enumerate(queries, start=1):
        assumptions, extra_clauses = query_gate(q)
        for c in extra_clauses:
            solver.add_clause(c)
        sat = solver.solve(assumptions=assumptions)
        ad6_reach[(q['source'], q['probe'])] = bool(sat)
        if i % 40 == 0 or i == len(queries):
            print("  [%d/%d] elapsed %.1fs" % (i, len(queries), time.perf_counter() - t0), flush=True)
    total_time = time.perf_counter() - t0
    print("solved all %d pairs in %.2fs (%.4fs/query)" %
          (len(queries), total_time, total_time / len(queries)), flush=True)

    # Same shape as test_ad6_wl_stanford.py's setUpClass: cls.reach =
    # {probe_base: set(source_base for source in sources if reachable and
    # source_base != probe_base)}.
    reach = {
        _base(p): set(
            _base(s) for s in sources
            if ad6_reach.get((s, p), False) and _base(s) != _base(p)
        )
        for p in probes
    }

    print("\n-- running the live NetPlumber worker (real oracle, not reachable.json) --", flush=True)
    sys.path.insert(0, FAVE_ROOT)
    cwd = os.getcwd()
    os.chdir(FAVE_ROOT)
    try:
        from bench.apkeep_convergence import _emit_worker
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="ad6_stanford_np_") as tmp:
            np_matrix = _emit_worker("netplumber", None, os.path.join(tmp, "np.json"))
        print("NetPlumber worker: %.2fs" % (time.perf_counter() - t0), flush=True)
    finally:
        os.chdir(cwd)

    np_reach = {role: set(srcs) for role, srcs in np_matrix.items()}

    diffs = {}
    for role in sorted(set(reach) | set(np_reach)):
        got = reach.get(role, set())
        exp = np_reach.get(role, set())
        if got != exp:
            diffs[role] = {"ad6_only": sorted(got - exp), "np_only": sorted(exp - got)}

    print("\n-- RESULT --", flush=True)
    print("roles compared: %d" % len(set(reach) | set(np_reach)), flush=True)
    print("roles with a diff: %d" % len(diffs), flush=True)
    if diffs:
        print("DIFFS (ad6-via-incremental-lever vs. live NetPlumber):", flush=True)
        for role, d in diffs.items():
            print("  %s: ad6_only=%s np_only=%s" % (role, d["ad6_only"], d["np_only"]), flush=True)
    else:
        print("EXACT MATCH: ad6 (via the incremental lever) == live NetPlumber on the full real "
              "wl_stanford data plane.", flush=True)
