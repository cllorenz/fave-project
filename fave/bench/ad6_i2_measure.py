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

""" AD6_PLAN.md §5.5 C1/C2: wl_i2 (Internet2) plain-mode differential +
tractability measurement -- the i2 counterpart to `bench/ad6_faithful_measure.py`
(wl_stanford's own B3 script), same instrumentation (instantiate/DIMACS-build/
solve split, CNF clause count, peak RSS), but PLAIN mode (faithful_vlan=False --
i2's out-tables are a clean dst-IP FIB, in-tables collapse to a single internal
port, no VLAN modelling needed per §5.5's own C3 gate) and against i2's full
77,841-route model directly (no router-subsetting tool exists for i2, unlike
Stanford's induced N=2/3/5 slices -- see AD6_PLAN.md §5.5).

C1 is the differential: does ad6's plain-mode reachability match
`bench/wl_i2/reachable.json` (the SAME oracle test_apkeep_i2.py validates
FaVe+APKeep against -- full mesh, 72/72 pairs reachable)? C2 is this same run's
own timing/clause-count/RSS instrumentation, since C1 already requires the full
build+solve.

ENVIRONMENT GUARDRAIL (AD6_PLAN.md, cross-cutting guardrails): wall-clock/
peak-RSS numbers from this script are only trusted on the controlled bare-metal
environment -- a sandboxed (yolobox) run can confirm the model builds/solves
correctly and give a DIRECTIONAL signal, but is never the tractability verdict
this stage's GO/NO-GO gate needs.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/ad6_i2_measure.py --out i2_plain.json
"""

import argparse
import json
import logging
import os
import resource
import sys
import time

sys.setrecursionlimit(10 ** 6)

_HERE = os.path.dirname(os.path.abspath(__file__))     # .../fave/bench
_FAVE = os.path.dirname(_HERE)                          # .../fave
_ROOT = os.path.dirname(_FAVE)                           # repo root
_AD6 = os.path.join(_ROOT, 'ad6')

_I2_PREFIX = os.path.join("bench", "wl_i2", "i2-json")
_ORACLE = os.path.join("bench", "wl_i2", "reachable.json")


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _peak_rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def _build_ir():
    """ AD6_PLAN.md §5.5 C0/C1: Ad6Adapter._build_ir() output for the real,
    full-scale wl_i2 model, faithful_vlan=False (plain mode -- see §5.5 C3:
    whether faithful-VLAN modelling is even needed for i2 is gated on
    whether plain mode already matches the oracle, so this script never
    turns faithful_vlan on). """
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("ad6_i2_measure")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, faithful_vlan=False)

    files = {"topology": "device_topology.json", "routes": "routes.json",
             "policies": "probes.json", "sources": "sources.json"}
    with InProcessFaVe(engine) as fave:
        fave.replay(_I2_PREFIX, files=files)
        sources = sorted(engine._generators)
        probes = sorted(engine._probes)
        ir = engine._build_ir()
    return ir, sources, probes


def _checkpoint(result, out_path, stage):
    """ Write progress-so-far to out_path and stderr after each phase, so a
    process killed mid-run (observed: a background nohup survives SIGHUP but
    not a sandbox/session teardown SIGKILL) still leaves a usable partial
    result instead of the silent zero-output loss hit on the first attempt. """
    result["status"] = "running:%s" % stage
    print("[checkpoint] %s wall_s=%.1f peak_rss_mb=%.1f" % (
        stage, time.time() - result["_wall0"], _peak_rss_mb()), file=sys.stderr, flush=True)
    if out_path:
        payload = {k: v for k, v in result.items() if not k.startswith("_")}
        with open(out_path, "w") as fh:
            json.dump(payload, fh, indent=2)


def measure(out_path, skip_acyclic=False):
    result = {"bench": "i2", "engine": "ad6", "faithful_vlan": False}
    wall0 = time.time()
    result["_wall0"] = wall0

    ir, sources, probes = _build_ir()
    result["sources"] = len(sources)
    result["probes"] = len(probes)
    result["devices"] = len(ir["devices"])
    result["fwd_rules"] = len(ir["fwd_rules"])
    _checkpoint(result, out_path, "ir_built")

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
        _checkpoint(result, out_path, "kripke_built")

        result["skip_acyclic"] = skip_acyclic
        combined = deepcopy(encoding)
        if skip_acyclic:
            # AD6_PLAN.md §5.5 C1/C2 finding: i2's Kripke graph has one giant
            # non-trivial SCC (99.3% of nodes), so _CreateAcyclicConstraints
            # doesn't get Stanford's "orders of magnitude" cut and did not
            # complete within 7-14 min in this environment. This path is a
            # cheap, ORIENTATION-ONLY check (does plain reachability match the
            # oracle at all, ignoring the floating-cycle soundness fix) -- NOT
            # a soundness-complete C1 result on its own.
            result["acyclic_constraint_s"] = None
            result["acyclic_extra_clauses"] = 0
        else:
            t0 = time.time()
            acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
            result["acyclic_constraint_s"] = round(time.time() - t0, 3)
            result["acyclic_extra_clauses"] = len(acyclic_constraints)
            _checkpoint(result, out_path, "acyclic_constraints_built")
            combined[0].extend(deepcopy(acyclic_constraints))

        t0 = time.time()
        adapter = MiniSATAdapter()
        variables, dimacs_clauses = adapter._ConvertToDIMACS(combined)
        result["dimacs_s"] = round(time.time() - t0, 3)
        result["variable_count"] = len(variables)
        result["clause_count"] = len(dimacs_clauses)
        _checkpoint(result, out_path, "dimacs_converted")

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
        _checkpoint(result, out_path, "solver_loaded")

        queries = [{"source": s, "probe": p} for p in probes for s in sources]
        result["query_count"] = len(queries)

        ad6_reach = {}
        t0 = time.time()
        for qi, q in enumerate(queries):
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
            if (qi + 1) % 10 == 0:
                result["queries_done"] = qi + 1
                _checkpoint(result, out_path, "querying")
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

    # C1: differential vs the oracle (fave/bench/wl_i2/reachable.json)
    oracle_path = os.path.join(_FAVE, _ORACLE)
    if "reach_matrix" in result and os.path.isfile(oracle_path):
        oracle = json.load(open(oracle_path))
        ad6_m = {p: set(srcs) for p, srcs in result["reach_matrix"].items()}
        or_m = {p: set(srcs) for p, srcs in oracle.items()}
        probes_u = set(ad6_m) | set(or_m)
        missing = {p: sorted(or_m.get(p, set()) - ad6_m.get(p, set()))
                   for p in probes_u if or_m.get(p, set()) - ad6_m.get(p, set())}
        extra = {p: sorted(ad6_m.get(p, set()) - or_m.get(p, set()))
                 for p in probes_u if ad6_m.get(p, set()) - or_m.get(p, set())}
        result["oracle_missing"] = missing
        result["oracle_extra"] = extra
        result["oracle_match"] = not missing and not extra

    result.pop("_wall0", None)
    printable = {k: v for k, v in result.items() if k != "reach_matrix"}
    print(json.dumps(printable, indent=2))
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=2)
        print("wrote %s" % out_path, file=sys.stderr)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", help="write the result JSON here")
    p.add_argument("--skip-acyclic", action="store_true",
                    help="orientation-only: skip _CreateAcyclicConstraints (cheap, but NOT "
                         "a soundness-complete C1 result -- see AD6_PLAN.md Sec 5.5)")
    args = p.parse_args(argv)
    measure(args.out, skip_acyclic=args.skip_acyclic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
