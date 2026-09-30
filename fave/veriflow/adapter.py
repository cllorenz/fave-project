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

""" VeriFlow-FR as a FaVe verification engine (VERIFLOW_PLAN.md V1).

The engine half: `veriflow.translate.Translator` records and translates the
models, this loads the IR into the native engine (`libveriflow_fr`, built by
veriflow_fr/python/build_libveriflow_fr.sh) and answers FaVe's checks in BULK
mode: everything is loaded, then each check is answered by Q21 -- the check's
packet set (the source's header space, restricted by its condition) stands in
for VeriFlow's "new rule", its ECs are computed network-wide, and their
forwarding graphs are walked from where the source enters the network.

A check (source, probe, negated, condition) is violated as NetPlumber's is
(`NetPlumber::check_compliance`): must-reach and no packet of the set is
delivered at the probe, or must-not-reach and some packet is. Results are
(source, probe, must_reach, condition) name tuples, the shape APKeepAdapter
reports.
"""

import os
import sys
import time

from typing import Any, Dict, List, Optional, Set, Tuple

from aggregator.abstract_engine import AbstractVerificationEngine
from veriflow.translate import Ir, Translator, Unsupported

_LIB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "veriflow_fr", "python"))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

try:
    import libveriflow_fr  # type: ignore
except ImportError:  # pragma: no cover - only when the .so is not built
    libveriflow_fr = None  # type: ignore


def available() -> bool:
    """ Whether the native engine is built. """
    return libveriflow_fr is not None


class DidNotFinish(Exception):
    """ A check could not be answered within the declared budget (VERIFLOW_PLAN.md
    Q22): reported as such, never as "no violation". Carries where it stopped. """

    def __init__(self, source: str, table: str, predicted: float, budget: int,
                 single_table: bool = True,
                 top: Optional[List[Tuple[str, int]]] = None) -> None:
        cause = ("that table alone would slice %.3g local ECs" % predicted
                 if single_table else
                 "the running total ran out there; where the work went: %s"
                 % ", ".join("%s %d" % t for t in (top or [])))
        super().__init__(
            "VeriFlow-FR did not finish the check from %s: past the budget of %d "
            "local ECs at %s -- %s (Q22)" % (source, budget, table, cause))
        self.source, self.table, self.predicted, self.budget = source, table, predicted, budget
        self.single_table, self.top = single_table, top or []


class VeriFlowAdapter(Translator, AbstractVerificationEngine):
    """ FaVe model -> VeriFlow-FR, bulk mode.

    `slicing` is Q22's stamp: "device" (the thesis's algorithm, T §3.1.3, and
    the only one that follows rewrites) or "network" (the paper's, kept for the
    rewrite-free calibration workloads). `budget` bounds the local ECs one check
    set may slice (0: none); past it, check_compliance raises DidNotFinish.
    `revisit` is Q4's: "state" (default) or "path". """

    def __init__(self, logger: Any = None, invert_lpm: bool = False,
                 slicing: str = "device", budget: int = 0,
                 revisit: str = "state") -> None:
        if slicing not in ("device", "network"):
            raise ValueError("slicing is 'device' or 'network', not %r" % slicing)
        if revisit not in ("path", "state"):
            raise ValueError("revisit is 'path' or 'state', not %r" % revisit)
        if libveriflow_fr is None:
            raise RuntimeError(
                "libveriflow_fr is not built; run "
                "veriflow_fr/python/build_libveriflow_fr.sh")
        Translator.__init__(self, invert_lpm=invert_lpm)
        self.logger = logger
        self.slicing = slicing
        self.budget = budget
        #: Q4 (owner, 2026-09-30): "state", the thesis's rule, by default --
        #: a walk stops at a (table, arrival, packet set) it has reached before.
        #: "path" is NetPlumber's (a path revisiting a table stops, whatever the
        #: header), kept for parity runs; it loses deliveries that legitimately
        #: pass a table twice (test/test_revisit_router_on_a_stick.py).
        self.revisit = revisit
        #: per check set answered: (source, local ECs sliced, states expanded)
        self.work: List[Tuple[str, int, int]] = []
        self._results: List[Tuple[str, str, bool, Any]] = []
        self.ir: Optional[Ir] = None
        self.net: Any = None
        self._built_for: Optional[Tuple[Any, ...]] = None
        #: seconds per phase of the last check_compliance: translate, load, query
        self.timings: Dict[str, float] = {}

    # -- building --------------------------------------------------------------

    def build(self, extra_fields: Any = ()) -> None:
        """ Translate what was recorded and load it into a fresh engine. """
        key = (len(self._models), len(self._links), len(self._generators),
               len(self._probes), frozenset(extra_fields))
        if self._built_for == key:
            return
        t0 = time.perf_counter()
        ir = self.translate(extra_fields)
        ir.stamps["vf_slicing"] = self.slicing
        ir.stamps["vf_budget"] = self.budget
        ir.stamps["vf_revisit"] = self.revisit
        t1 = time.perf_counter()
        net = libveriflow_fr.Network(ir.fields)
        for tid in sorted(set(ir.tables.values())):
            net.add_table(tid)
        for port, tid in sorted(ir.port_table.items()):
            net.add_port(port, tid)
        for a, b in ir.links:
            net.add_link(a, b)
        for r in ir.rules:
            net.load_rule(r.id, r.table, r.priority, r.in_port, r.match,
                          r.out_ports, r.consume, r.rewrites)
        t2 = time.perf_counter()
        self.ir, self.net, self._built_for = ir, net, key
        self.timings = {"translate": t1 - t0, "load": t2 - t1}

    # -- checking --------------------------------------------------------------

    def check_compliance(self, rules: Any) -> None:
        """ Answer the checks (probe -> [(source, negated, condition)]). """
        cond_fields = {f.name for checks in rules.values()
                       for (_src, _neg, cond) in checks for f in cond}
        self.build(sorted(cond_fields))
        ir = self.ir
        assert ir is not None

        t0 = time.perf_counter()
        # Each distinct (source, condition) is one query; each distinct query
        # SET is answered once, for every start of every source that has it.
        keys: Dict[Tuple[str, Tuple[Any, ...]], List[str]] = {}
        for checks in rules.values():
            for src, negated, cond in checks:
                if negated is False and any(f.negated for f in cond):
                    raise Unsupported(
                        "a negated condition on a must-reach check (%s): its "
                        "complement expands to several sets, and requiring "
                        "reachability under each is stronger than the question "
                        "-- refused, as NetPlumber refuses it (Q17)" % src)
                key = (src, tuple((f.name, str(f.value), f.negated) for f in cond))
                if key in keys:
                    continue
                if src not in ir.generators:
                    raise Unsupported("check names unknown source %s" % src)
                _starts, sets = ir.generators[src]
                keys[key] = [s for base in sets
                             for s in self.condition_sets(ir, base, cond)]

        by_set: Dict[str, List[Tuple[str, Tuple[Any, ...]]]] = {}
        for key, sets in keys.items():
            for qs in sets:
                by_set.setdefault(qs, []).append(key)
        delivered: Dict[Tuple[str, Tuple[Any, ...]], Set[int]] = {k: set() for k in keys}
        for qs, owners in by_set.items():
            starts: List[Tuple[int, int]] = []
            owner_of: List[Tuple[str, Tuple[Any, ...]]] = []
            for key in owners:
                for start in ir.generators[key[0]][0]:
                    starts.append(start)
                    owner_of.append(key)
            if self.slicing == "network":
                answers = self.net.deliveries(qs, starts)
            else:
                (answers, finished, stopped_at, predicted, single, local_ecs, hops,
                 per_table) = self.net.local_deliveries(
                     qs, starts, self.budget, self.revisit == "state")
                self.work.append((owners[0][0], local_ecs, hops))
                if not finished:
                    names = {v: k for k, v in ir.tables.items()}
                    top = sorted(per_table.items(), key=lambda kv: -kv[1])[:3]
                    raise DidNotFinish(owners[0][0], names.get(stopped_at, str(stopped_at)),
                                       predicted, self.budget, single,
                                       [(names.get(t, str(t)), n) for t, n in top])
            for key, tables in zip(owner_of, answers):
                delivered[key].update(tables)

        for dst, checks in rules.items():
            if dst not in ir.probes:
                raise Unsupported("check names unknown probe %s" % dst)
            table = ir.probes[dst]
            for src, negated, cond in checks:
                key = (src, tuple((f.name, str(f.value), f.negated) for f in cond))
                must_reach = not negated
                arrives = table in delivered[key]
                if must_reach != arrives:
                    self._results.append((src, dst, must_reach, cond))
        self.timings["query"] = time.perf_counter() - t0

    def get_compliance_results(self) -> List[Tuple[str, str, bool, Any]]:
        return list(self._results)

    def clear_results(self) -> None:
        self._results = []

    def stop(self, *_args: Any, **_kwargs: Any) -> None:
        pass
