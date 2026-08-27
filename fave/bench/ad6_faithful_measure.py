#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" AD6_PLAN.md §5.4 Stage B3: faithful-VLAN wl_stanford tractability
measurement -- the ad6-side counterpart to `bench/faithful_bdd_measure.py`
(BDD-APKeep's own faithful-VLAN measurement driver), reusing the SAME
induced-subnetwork protocol (`apkeep_convergence._filter_model`, the same
`--routers` subsets: N=2 bbra_rtr,rozb_rtr / N=3 +roza_rtr / N=5
+soza_rtr,sozb_rtr, per `APKEEP_NDD_EVAL.md`'s own table) so the two
backends' numbers are directly comparable at the same N.

Reports what §5.4 Stage B's own spec asks for: the instantiate/DIMACS-
build/solve split, CNF clause count, and peak RSS -- ad6's analogue of
APKeep's build/query split, `ap_num`, and peak JVM heap. Uses ad6's own
`src.*` package tree DIRECTLY (not through the production
Ad6Adapter/fave_bridge.py subprocess bridge) for instrumentation access to
the DIMACS conversion and the persistent incremental solver -- the same
discipline `ad6_encoding_bench/axis8d_stanford_netplumber_diff.py` already
established for exactly this kind of measurement-only script (read-only
use of both `fave/` and `ad6/`'s existing modules; nothing in either
production path is modified or imported into the other's normal runtime).

ENVIRONMENT GUARDRAIL (AD6_PLAN.md, cross-cutting guardrails): wall-clock/
peak-RSS numbers from this script are only trusted on the controlled
bare-metal environment -- a sandboxed (yolobox) run can confirm the model
builds/solves correctly and give a DIRECTIONAL signal, but is never the
tractability verdict Stage B3's GO/NO-GO gate needs.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/ad6_faithful_measure.py --routers bbra_rtr,rozb_rtr --out n2.json
  python3 bench/ad6_faithful_measure.py --routers bbra_rtr,roza_rtr,rozb_rtr --out n3.json
  python3 bench/ad6_faithful_measure.py \
      --routers bbra_rtr,roza_rtr,rozb_rtr,soza_rtr,sozb_rtr --out n5.json
  python3 bench/ad6_faithful_measure.py --out n16.json   # full model, no --routers
"""

import argparse
import json
import logging
import os
import resource
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))     # .../fave/bench
_FAVE = os.path.dirname(_HERE)                          # .../fave
_ROOT = os.path.dirname(_FAVE)                           # repo root
_AD6 = os.path.join(_ROOT, 'ad6')

sys.setrecursionlimit(10 ** 6)

_STANFORD_PREFIX = os.path.join("bench", "wl_stanford", "stanford-json")


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _peak_rss_mb():
    """ Peak resident set size across THIS process's lifetime so far
    (ru_maxrss is already a high-water mark, unlike a point-in-time RSS
    read -- the direct analogue of faithful_bdd_measure.py's
    _peak_heap_bytes, just OS-level instead of JVM-level since ad6 has no
    separate heap to query). Linux reports ru_maxrss in KB. """
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def _build_ir(routers):
    """ Ad6Adapter._build_ir() output for the (possibly induced-subnetwork)
    real wl_stanford model, faithful_vlan=True -- mirrors
    faithful_bdd_measure.py's _prepare_replay_dir + measure()'s own replay
    step, but stops at the IR (this script drives ad6's OWN build/solve
    machinery directly afterwards, not through the subprocess bridge). """
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("ad6_faithful_measure")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, faithful_vlan=True)

    tmp = None
    if routers:
        from bench.apkeep_convergence import _filter_model, _load_model, _write_model
        model = _filter_model(_load_model(), set(routers))
        tmp = tempfile.TemporaryDirectory(prefix="ad6_faithful_")
        _write_model(model, tmp.name)
        replay_dir = tmp.name
    else:
        replay_dir = _STANFORD_PREFIX

    files = {"topology": "device_topology.json", "routes": "routes.json",
             "policies": "probes.json", "sources": "sources.json"}
    try:
        with InProcessFaVe(engine) as fave:
            fave.replay(replay_dir, files=files)
            sources = sorted(engine._generators)
            probes = sorted(engine._probes)
            ir = engine._build_ir()
    finally:
        if tmp is not None:
            tmp.cleanup()
    return ir, sources, probes


def measure(routers, out_path):
    result = {
        "bench": "stanford", "engine": "ad6", "faithful_vlan": True,
        "routers": sorted(routers) if routers else None,
    }
    wall0 = time.time()

    ir, sources, probes = _build_ir(routers)
    result["sources"] = len(sources)
    result["probes"] = len(probes)
    result["devices"] = len(ir["devices"])

    sys.path.insert(0, _AD6)
    from src.core.instantiator import Instantiator
    from src.parser import favemodel
    from src.solver.minisat import MiniSATAdapter
    from src.xml.xmlutils import XMLUtils
    from pysat.solvers import Minisat22
    from copy import deepcopy

    cwd = os.getcwd()
    os.chdir(_AD6)
    try:
        t0 = time.time()
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, encoding = favemodel.instantiate_base(config, ir)
        result["kripke_nodes"] = len(list(kripke.IterNodes()))
        result["build_s"] = round(time.time() - t0, 3)

        # AD6_PLAN.md §6/§5.4 B1: the same SCC-scoped acyclic rank
        # constraints IncrementalSession bakes in unconditionally --
        # replicated here (not via IncrementalSession itself) so this
        # script can report the DIMACS conversion and clause count
        # directly, the same instrumentation axis8d's DimacsBridge used.
        t0 = time.time()
        acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
        result["acyclic_constraint_s"] = round(time.time() - t0, 3)
        result["acyclic_extra_clauses"] = len(acyclic_constraints)

        combined = deepcopy(encoding)
        combined[0].extend(deepcopy(acyclic_constraints))

        t0 = time.time()
        adapter = MiniSATAdapter()
        variables, dimacs_clauses = adapter._ConvertToDIMACS(combined)
        result["dimacs_s"] = round(time.time() - t0, 3)
        result["variable_count"] = len(variables)
        result["clause_count"] = len(dimacs_clauses)

        name_to_index = {name: i + 1 for i, name in enumerate(variables)}
        next_index = [len(variables) + 1]

        def index_for(name):
            idx = name_to_index.get(name)
            if idx is None:
                idx = next_index[0]
                name_to_index[name] = idx
                next_index[0] += 1
            return idx

        def literal(xml_var):
            idx = index_for(xml_var.attrib[XMLUtils.ATTRNAME])
            return -idx if xml_var.attrib.get(XMLUtils.ATTRNEGATED) == 'true' else idx

        def or_gate(xml_vars):
            lits = [literal(v) for v in xml_vars]
            if not lits:
                aux = next_index[0]
                next_index[0] += 1
                return aux, [[-aux]]
            if len(lits) == 1:
                return lits[0], []
            aux = next_index[0]
            next_index[0] += 1
            return aux, [[-lit, aux] for lit in lits] + [[-aux] + lits]

        t0 = time.time()
        solver = Minisat22(bootstrap_with=dimacs_clauses)
        result["solver_load_s"] = round(time.time() - t0, 3)

        queries = [{"source": s, "probe": p} for p in probes for s in sources]
        result["query_count"] = len(queries)

        ad6_reach = {}
        t0 = time.time()
        for q in queries:
            source = favemodel.gen_entry_key(q['source'])
            destination = favemodel.query_destination_key(q['probe'], ir)
            f_trans = [XMLUtils.CreateTransition(source, t, flag)
                       for t, flag in kripke.IterFTransitions(source)]
            b_trans = [XMLUtils.CreateTransition(p, destination, flag)
                       for p, flag in kripke.IterBTransitions(destination)]
            src_lit, src_clauses = or_gate(f_trans)
            dst_lit, dst_clauses = or_gate(b_trans)
            for clause in src_clauses + dst_clauses:
                solver.add_clause(clause)
            sat = bool(solver.solve(assumptions=[src_lit, dst_lit]))
            ad6_reach[(q['source'], q['probe'])] = sat
        result["query_s"] = round(time.time() - t0, 3)
        solver.delete()

        reach = {
            _base(p): sorted(
                _base(s) for s in sources
                if ad6_reach.get((s, p), False) and _base(s) != _base(p)
            )
            for p in probes
        }
        result["reachable_pairs"] = sum(len(v) for v in reach.values())
        result["reach_matrix"] = reach
        result["status"] = "completed"
    finally:
        os.chdir(cwd)
        result["wall_s"] = round(time.time() - wall0, 3)
        result["peak_rss_mb"] = _peak_rss_mb()

    print(json.dumps({k: v for k, v in result.items() if k != "reach_matrix"}, indent=2))
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=2)
        print("wrote %s" % out_path, file=sys.stderr)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--routers", help="comma-separated router bases -> reduced "
                                      "induced slice (matches apkeep_convergence's "
                                      "own subsetting); omit for the full 16-router model")
    p.add_argument("--out", help="write the result JSON here")
    args = p.parse_args(argv)
    routers = [r for r in args.routers.split(",") if r] if args.routers else None
    measure(routers, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
