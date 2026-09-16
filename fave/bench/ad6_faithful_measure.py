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

from bench.ad6_stamp import (
    SOLVERS, admission_stamp, needs_fresh_per_query, solver_class)

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
    # AD6_PLAN.md §9.3 Phase 5: the adapter default flipped to 'structural' at
    # the Phase 5 gate. This driver's archived numbers were all measured on the
    # SEMANTIC path, so it pins that explicitly -- leaving it implicit would have
    # re-measured every one of them silently, which is exactly what the
    # generality-debt gate forbids (a measurement-affecting choice is a stamped
    # field, never a habit). Re-measuring structurally is a deliberate act: change
    # this line and re-run, do not inherit a new default.
    from ad6.adapter import Ad6Adapter, TRANSLATION_SEMANTIC
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("ad6_faithful_measure")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, faithful_vlan=True,
                        translation=TRANSLATION_SEMANTIC)

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


def _config_stamp(flow_path, solver_name="minisat22", lite_acyclic=False,
                  fresh_per_query=False):
    """ AD6_PLAN.md generality-debt items 1/2/8, added 2026-09-11: the
    measurement-affecting configuration behind a wl_stanford result.

    Every archived `ad6_faithful_*.json` predating this carried NONE of these
    fields, so the measured flow-vs-rank result rested on inferring each
    run's configuration from the driver's source and the file's mtime -- while
    `bench/ad6_i2_measure.py` stamped all of it, making the two benchmarks'
    numbers uncomparable in precisely the way the stamping gate exists to
    prevent.

    These were CONSTANTS until 2026-09-11 -- this driver offered no `--solver`
    and no `--lite-acyclic`, so every wl_stanford number was Minisat22 plus the
    general acyclic encoding while every wl_i2 number was typically Cadical195
    plus the lite one, and the two were quoted side by side. Both are now
    selectable, which is what an apples-to-apples cross-benchmark table needs;
    the stamp records what actually ran either way. """
    return {
        # Spelled exactly as `bench/ad6_i2_measure.py` spells it -- one shared
        # vocabulary in `bench/ad6_stamp.py`, so the two drivers' result files
        # compare directly (pinned by test).
        "solver": solver_name,
        # Derived, not a second source of truth: `--flow-path` REPLACES the
        # rank encoding, so the grounding is a function of that one switch.
        "grounding": "flow" if flow_path else "rank",
        # General `_CreateAcyclicConstraints` vs the clause-identical
        # `_CreateAcyclicConstraintsLite`. wl_i2 CANNOT run the general path
        # (it OOMs at that scale) so its runs are all lite; wl_stanford can run
        # either, and the difference has to be visible when the two are quoted
        # together. Meaningless under --flow-path, which builds neither.
        "lite_acyclic": bool(lite_acyclic) and not flow_path,
        "skip_acyclic": bool(flow_path),
        # Forced by --flow-path (the flow constraint names its endpoints, so
        # choosing it chooses a fresh solver per query -- generality-debt item
        # 8) and by any solver whose wrapper ignores assumptions; otherwise a
        # free choice, and a DIFFERENT measurement either way (item 3).
        "fresh_per_query": bool(fresh_per_query or flow_path),
        # `_build_ir` constructs `Ad6Adapter(log, faithful_vlan=True)` and never
        # passes `probe_untag`, so it is off here -- the cross-engine parity
        # choice of generality-debt item 4, stamped rather than assumed.
        "probe_untag": False,
    }


def measure(routers, out_path, flow_path=False, solver_name="minisat22",
            lite_acyclic=False, fresh_per_query=False):
    result = {
        "bench": "stanford", "engine": "ad6", "faithful_vlan": True,
        "routers": sorted(routers) if routers else None,
        # AD6_PLAN.md §5.4 B1: WHICH grounding constraint produced these
        # verdicts. `faithful_vlan: true` alone no longer identifies the run --
        # the rank/acyclic encoding and the per-query single-unit s-t flow are
        # two different mechanisms for the same soundness job.
        "flow_path": flow_path,
    }
    fresh_per_query = bool(fresh_per_query or flow_path
                           or needs_fresh_per_query(solver_name))
    result.update(_config_stamp(flow_path, solver_name=solver_name,
                                lite_acyclic=lite_acyclic,
                                fresh_per_query=fresh_per_query))
    wall0 = time.time()

    ir, sources, probes = _build_ir(routers)
    result["sources"] = len(sources)
    result["probes"] = len(probes)
    result["devices"] = len(ir["devices"])
    # The per-(port, VLAN) ingress admission relation, by the SAME rule the
    # wl_i2 driver stamps (shared in bench/ad6_stamp.py). This is the field
    # whose absence forced the port-scoped/pre-fix distinction between two
    # archived wl_stanford runs to be inferred from their clause counts.
    result.update(admission_stamp(ir))

    sys.path.insert(0, _AD6)
    from src.core.instantiator import Instantiator
    from src.parser import favemodel
    from src.solver.minisat import MiniSATAdapter
    from src.xml.xmlutils import XMLUtils
    from copy import deepcopy

    solver_cls = solver_class(solver_name)

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
        combined = deepcopy(encoding)
        lite_clauses = None
        if flow_path:
            # AD6_PLAN.md §5.4 B1: the flow constraint REPLACES the rank
            # encoding rather than supplementing it -- both close the same
            # SECRYPT'15 grounding gap, and building both would just pay twice.
            # It is per-query (source/destination appear in it), so it is added
            # to a FRESH solver below instead of to the shared base.
            result["acyclic_constraint_s"] = None
            result["acyclic_extra_clauses"] = 0
        elif lite_acyclic:
            # AD6_PLAN.md §5.5: the memory-lite reimplementation. It emits the
            # IDENTICAL clause set (pinned by
            # testAcyclicRankConstraintLiteMatchesGeneralEncoding) as plain
            # (name, negated) tuples rather than an lxml formula tree per edge,
            # so it CANNOT be spliced into `combined[0]` -- it is resolved to
            # DIMACS ints after the base conversion below, exactly as
            # `bench/ad6_i2_measure.py` does it. Selectable here so a
            # wl_stanford number can be produced under the same encoding wl_i2
            # is FORCED onto, which is what makes the two comparable.
            t0 = time.time()
            lite_clauses = Instantiator._CreateAcyclicConstraintsLite(kripke)
            result["acyclic_constraint_s"] = round(time.time() - t0, 3)
            result["acyclic_extra_clauses"] = len(lite_clauses)
        else:
            t0 = time.time()
            acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
            result["acyclic_constraint_s"] = round(time.time() - t0, 3)
            result["acyclic_extra_clauses"] = len(acyclic_constraints)
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

        if lite_clauses is not None:
            t0 = time.time()
            dimacs_clauses.extend(
                [-index_for(name) if negated else index_for(name)
                 for name, negated in clause]
                for clause in lite_clauses)
            del lite_clauses
            result["lite_dimacs_s"] = round(time.time() - t0, 3)
            result["variable_count"] = next_index[0] - 1
            result["clause_count"] = len(dimacs_clauses)

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
        solver = None if fresh_per_query else solver_cls(bootstrap_with=dimacs_clauses)
        result["solver_load_s"] = None if solver is None else round(time.time() - t0, 3)

        queries = [{"source": s, "probe": p} for p in probes for s in sources]
        result["query_count"] = len(queries)

        ad6_reach = {}
        flow_total = 0
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
            if fresh_per_query:
                # A FRESH solver per query, for either of two reasons. Under
                # --flow-path the flow constraint names THIS query's endpoints,
                # so reusing one solver would leave the previous query's
                # constraints asserted and answer this one against the wrong
                # endpoints -- a wrong verdict, not a crash. Under a solver
                # whose wrapper ignores `assumptions` it is the only way the
                # endpoints bind at all. Either way the endpoints go in as UNIT
                # CLAUSES rather than assumptions.
                q_solver = solver_cls(bootstrap_with=dimacs_clauses)
                for clause in src_clauses + dst_clauses:
                    q_solver.add_clause(clause)
                q_solver.add_clause([src_lit])
                q_solver.add_clause([dst_lit])
                if flow_path:
                    flow_clauses = Instantiator._CreateFlowPathConstraints(
                        kripke, source, destination)
                    flow_total += len(flow_clauses)
                    for clause in flow_clauses:
                        q_solver.add_clause([
                            -index_for(n) if neg else index_for(n) for n, neg in clause])
                sat = bool(q_solver.solve())
                q_solver.delete()
            else:
                for clause in src_clauses + dst_clauses:
                    solver.add_clause(clause)
                sat = bool(solver.solve(assumptions=[src_lit, dst_lit]))
            ad6_reach[(q['source'], q['probe'])] = sat
        result["query_s"] = round(time.time() - t0, 3)
        if flow_path:
            result["flow_path_clauses_total"] = flow_total
            result["flow_path_clauses_per_query"] = (
                flow_total // len(queries) if queries else 0)
        # Keyed off the solver itself, not off flow_path: --fresh-per-query
        # also leaves no persistent solver to release, and each query's own
        # solver is already deleted in the loop above.
        if solver is not None:
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
    p.add_argument("--flow-path", action="store_true",
                   help="ground each query with a single-unit s-t FLOW constraint "
                        "(Instantiator._CreateFlowPathConstraints) INSTEAD of the "
                        "rank/acyclic encoding -- AD6_PLAN.md Sec 5.4 B1. Implies a "
                        "fresh solver per query, since the constraint names that "
                        "query's own endpoints. The differential that validates it: "
                        "this must reproduce the rank encoding's reachable_pairs "
                        "exactly (165 on the full 16-router model).")
    p.add_argument("--solver", choices=SOLVERS, default="minisat22",
                   help="PySAT backend to load/solve with (default: minisat22, what "
                        "every archived wl_stanford result was produced under). Same "
                        "vocabulary as bench/ad6_i2_measure.py, so the two benchmarks' "
                        "result files compare directly -- AD6_PLAN.md's generality-debt "
                        "item 2.")
    p.add_argument("--lite-acyclic", action="store_true",
                   help="build the rank constraints with "
                        "Instantiator._CreateAcyclicConstraintsLite instead of the "
                        "general encoding. Clause-IDENTICAL by test, so this changes "
                        "cost and not verdicts; offered here because wl_i2 has no "
                        "choice (the general path OOMs at that scale), and comparing a "
                        "wl_stanford number against a wl_i2 one means matching the "
                        "encoding -- AD6_PLAN.md Sec 5.5, generality-debt item 1. "
                        "Ignored under --flow-path, which builds no rank constraints.")
    p.add_argument("--fresh-per-query", action="store_true",
                   help="bootstrap a FRESH solver per query, baking the endpoints in "
                        "as unit clauses, instead of reusing one persistent "
                        "assumption-based session. A DIFFERENT measurement, not a "
                        "second route to the same number (generality-debt item 3). "
                        "Implied by --flow-path and by any solver whose PySAT wrapper "
                        "ignores assumptions.")
    args = p.parse_args(argv)
    # Refused rather than resolved: either resolution would produce a
    # plausible-looking result file answering a different question than the
    # flags claim.
    if needs_fresh_per_query(args.solver) and not (args.fresh_per_query or args.flow_path):
        # This one cannot be left to the operator, because getting it wrong does
        # not fail. PySAT's Kissat wrapper drops `assumptions` with only a
        # RuntimeWarning (verified by experiment -- see bench/ad6_stamp.py), so
        # the persistent session would solve every query against the bare base
        # encoding and report everything reachable.
        p.error("--solver %s requires --fresh-per-query: PySAT's wrapper for it "
                "SILENTLY IGNORES assumptions, so the persistent session would drop "
                "each query's own source/destination literals and report everything "
                "reachable (AD6_PLAN.md Sec 5.5 C2 follow-up)" % args.solver)
    if args.lite_acyclic and args.flow_path:
        p.error("--lite-acyclic and --flow-path are mutually exclusive: the flow "
                "constraint REPLACES the rank encoding, so there would be no rank "
                "constraints for --lite-acyclic to build, and the run would stamp an "
                "encoding it never used (AD6_PLAN.md Sec 5.4 B1)")
    routers = [r for r in args.routers.split(",") if r] if args.routers else None
    measure(routers, args.out, flow_path=args.flow_path, solver_name=args.solver,
            lite_acyclic=args.lite_acyclic, fresh_per_query=args.fresh_per_query)
    return 0


if __name__ == "__main__":
    sys.exit(main())
