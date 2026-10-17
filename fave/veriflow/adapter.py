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

from aggregator.abstract_engine import AbstractVerificationEngine, UpdateRefused
from veriflow.translate import Ir, IrRule, Translator, Unsupported, scan_fields

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


#: TODO item 59, option c: the explored states a walk remembers under `state`
#: revisit (0: all). 4 M (owner, 2026-10-17, for D16): wl_stanford's first
#: check with tracking on takes 269 s at 4 M as unbounded, 1,270 s at 1 M
#: (calibration FINDINGS, results_inc_dev_fave_calibration_20261016); wl_tum's
#: worst walk (54.7 M states) holds 4.4 GB at 4 M, 1.3 GB at 1 M, 55.7 GB
#: unbounded (results_vf_tum_perf_20261015); 10 k costs wl_i2 +80 % local ECs.
DEFAULT_STATE_CACHE = 4_000_000

#: The selectable footprints of VERIFLOW_FOOTPRINT_SCOPE.md §4, as on APKeep
#: (APKEEP_FOOTPRINTS.md).
FOOTPRINT_MODES = ('witness', 'dead-ends')
#: Both modes, as on APKeep (owner, 2026-10-15, §4.5); () selects the coarse
#: footprint, kept as the ablation row
DEFAULT_FOOTPRINT = FOOTPRINT_MODES


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

    #: TODO item 31. Ours, from the NSDI'13 paper and the 2015 thesis alone,
    #: under the clean-room protocol of `VERIFLOW_PLAN.md` §5. A slow number
    #: from this engine is VeriFlow-FR's and never VeriFlow's -- which is the
    #: whole reason this value is not `authors`.
    IMPL = 'reimpl-literature'

    def __init__(self, logger: Any = None, invert_lpm: bool = False,
                 slicing: str = "device", budget: int = 0,
                 revisit: str = "state", fields: str = "4+10",
                 footprint: Optional[Tuple[str, ...]] = None,
                 witness_point: bool = True, early_exit: bool = True,
                 state_cache: int = DEFAULT_STATE_CACHE) -> None:
        if slicing not in ("device", "network"):
            raise ValueError("slicing is 'device' or 'network', not %r" % slicing)
        if revisit not in ("path", "state"):
            raise ValueError("revisit is 'path' or 'state', not %r" % revisit)
        if fields not in ("plain", "4+10"):
            raise ValueError("fields is 'plain' or '4+10', not %r" % fields)
        if libveriflow_fr is None:
            raise RuntimeError(
                "libveriflow_fr is not built; run "
                "veriflow_fr/python/build_libveriflow_fr.sh")
        if footprint is None:
            footprint = DEFAULT_FOOTPRINT
        unknown = [m for m in footprint if m not in FOOTPRINT_MODES]
        if unknown:
            raise ValueError("unknown footprint mode(s) %s; known: %s"
                             % (unknown, ', '.join(FOOTPRINT_MODES)))
        Translator.__init__(self, invert_lpm=invert_lpm)
        self.logger = logger
        #: VERIFLOW_FOOTPRINT_SCOPE.md §4: () is the coarse footprint (a source's
        #: explored walk; a hit re-checks every probe of it). 'witness': a
        #: delivered (source, probe) watches one path (§4.1); 'dead-ends': an
        #: undelivered one ignores changes that send packets nowhere (§4.2).
        #: Either mode reports (source, probe) pairs (§4.3).
        self.footprint = tuple(m for m in FOOTPRINT_MODES if m in footprint)
        #: §4.1: carry one concrete packet per hop (True), or test the hop's
        #: whole packet set (False -- coarser, kept for tests and the ablation)
        self.witness_point = witness_point
        self.slicing = slicing
        self.budget = budget
        #: Early exit (owner, 2026-10-16; ACCOMMODATIONS.md): with tracking
        #: off, a start's walk stops once every probe asked of its key is
        #: delivered -- the verdicts need nothing more. With tracking on the
        #: walk stays whole: the footprints and the delivered sets the
        #: selective re-check reads are the whole walk's. Off is the ablation.
        self.early_exit = early_exit
        #: starts whose walk stopped early, over the lifetime
        self.early_exits = 0
        #: TODO item 59, option c (owner, 2026-10-16): under `state` revisit,
        #: how many explored states a start remembers (0: all); the states on
        #: the walk's path always end a loop. Changes the work, never an answer.
        if state_cache < 0:
            raise ValueError("state_cache is a count of states, not %r" % state_cache)
        self.state_cache = state_cache
        #: Q4 (owner, 2026-09-30): "state", the thesis's rule, by default --
        #: a walk stops at a (table, arrival, packet set) it has reached before.
        #: "path" is NetPlumber's (a path revisiting a table stops, whatever the
        #: header), kept for parity runs; it loses deliveries that legitimately
        #: pass a table twice (test/test_revisit_router_on_a_stick.py).
        self.revisit = revisit
        #: D6 / V3b: "4+10" by default (T §3.2.2 generalised: exact-or-ANY fields
        #: scanned, finer rules excluded -- VeriFlow-FR's headline, D6), or
        #: "plain" (every field a trie dimension: the ablation)
        self.fields = fields
        self._scan: List[bool] = []
        #: per check set answered: (source, local ECs sliced, states expanded)
        self.work: List[Tuple[str, int, int]] = []
        self._results: List[Tuple[str, str, bool, Any]] = []
        self.ir: Optional[Ir] = None
        self.net: Any = None
        self._built_for: Optional[Tuple[Any, ...]] = None
        #: seconds per phase of the last check_compliance: translate, load, query
        self.timings: Dict[str, float] = {}
        # -- incremental updates (INCREMENTAL_PLAN.md §6.3) ---------------------
        #: whether walks record their footprint, and the last footprint per
        #: query set; the query sets of each (source, condition) asked
        self._tracking = False
        #: keyed (source, condition key, query set): one walk serves every
        #: source sharing a set, so its footprint is recorded for each of them
        #: -- a later walk for only SOME of them must not shrink the others'
        self._footprints: Dict[Tuple[Tuple[str, Tuple[Any, ...]], str], Any] = {}
        self._sets_of: Dict[Tuple[str, Tuple[Any, ...]], List[str]] = {}
        #: sources whose checks an update since the last take_affected can affect
        self._pending: Set[str] = set()
        # -- the finer footprints (VERIFLOW_FOOTPRINT_SCOPE.md §4) ----------------
        #: per (source, condition key): the probe tables its walks delivered
        #: at, and the probes ever checked with it (a selective re-check asks
        #: a subset, so this only grows)
        self._delivered: Dict[Tuple[str, Tuple[Any, ...]], Set[int]] = {}
        self._probes_of: Dict[Tuple[str, Tuple[Any, ...]], Set[str]] = {}
        #: per key, per probe table: the witness of a delivery and the tables
        #: its hops cross
        self._witness: Dict[Tuple[str, Tuple[Any, ...]], Dict[int, Tuple[Any, Set[int]]]] = {}
        #: per key, per probe name: ports a dead end left unlinked (§4.2)
        self._watch: Dict[Tuple[str, Tuple[Any, ...]], Dict[str, Set[int]]] = {}
        #: (source, probe) pairs an update since the last take_affected can affect
        self._pending_pairs: Set[Tuple[str, str]] = set()
        #: (node, tid, idx) -> engine rule ids, and id -> rule; built on the
        #: first update so a build from zero does none of this work
        self._rids: Optional[Dict[Tuple[str, str, int], List[int]]] = None
        self._rule_by_id: Dict[int, IrRule] = {}
        self._next_rid = 0
        #: set by the first update: a rebuild would now retranslate the model
        #: as it was recorded, without the updates, so it is refused
        self._updated = False
        #: devices removed by emptying (INCREMENTAL_PLAN.md §8.2): their
        #: tables and ports stay in the engine, without rules or links
        self._emptied: Set[str] = set()

    def configuration_stamp(self) -> Dict[str, Any]:
        """ The measurement-affecting choices behind this adapter's answers,
        logged by the aggregator next to the backend name (as ad6's is). The
        stamps only a built model can know are logged by `build`.

        `impl` used to be the literal here; it now comes from `IMPL`, which the
        base class reads, so that the four backends declare provenance ONE way
        instead of this one doing it by hand and the others not at all. """
        stamp = self.provenance()
        stamp.update({"vf_fields": self.fields,
                      # VERIFLOW_FOOTPRINT_SCOPE.md §4.5; [] is the coarse one
                      "footprint": list(self.footprint),
                      "witness_point": self.witness_point,
                      "vf_revisit": self.revisit, "vf_slicing": self.slicing,
                      "vf_budget": self.budget, "vf_early_exit": self.early_exit,
                      "vf_state_cache": self.state_cache,
                      # MEASUREMENT_RUN_PLAN.md §5.4's guardrail. It reached
                      # `Ir.stamps` already (`vf_invert_lpm`) but not here, so
                      # a CELL could not tell an inverted run from a faithful
                      # one -- the stamp was in the model's record and not in
                      # the measurement's. Always present, never only when set.
                      "vf_invert_lpm": self.invert_lpm})
        return stamp

    # -- building --------------------------------------------------------------

    def build(self, extra_fields: Any = ()) -> None:
        """ Translate what was recorded and load it into a fresh engine. """
        key = (len(self._models), len(self._links), len(self._generators),
               len(self._probes), frozenset(extra_fields))
        if self._built_for == key:
            return
        # A layout that already has every field asked for answers these checks
        # as well as a fresh one would: an extra field is ANY in every rule.
        # Without this, asking a SUBSET of the checks -- a selective
        # re-verification -- rebuilt the network for a narrower layout.
        if (self._built_for is not None and self.ir is not None
                and self._built_for[:4] == key[:4]
                and set(extra_fields) <= {name for name, _w in self.ir.fields}):
            return
        if self._updated:
            raise UpdateRefused(
                "VeriFlowAdapter: a rebuild after incremental updates would "
                "retranslate the model as recorded, without them (the checks "
                "need fields or the model changed: %s)" % (key,))
        t0 = time.perf_counter()
        ir = self.translate(extra_fields)
        ir.stamps["vf_slicing"] = self.slicing
        ir.stamps["vf_budget"] = self.budget
        ir.stamps["vf_revisit"] = self.revisit
        ir.stamps["vf_early_exit"] = self.early_exit
        ir.stamps["vf_state_cache"] = self.state_cache
        self._scan = scan_fields(ir) if self.fields == "4+10" else []
        ir.stamps["vf_fields"] = "plain" if not self._scan else "4+10:trie=%s,scan=%s" % (
            [n for (n, _w), sc in zip(ir.fields, self._scan) if not sc],
            [n for (n, _w), sc in zip(ir.fields, self._scan) if sc])
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
        self._footprints = {}
        self.timings = {"translate": t1 - t0, "load": t2 - t1}
        if self.logger is not None:
            self.logger.info("veriflow: built %d rules, stamps %s", len(ir.rules), ir.stamps)

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
        for dst, checks in rules.items():
            for src, negated, cond in checks:
                if negated is False and any(f.negated for f in cond):
                    raise Unsupported(
                        "a negated condition on a must-reach check (%s): its "
                        "complement expands to several sets, and requiring "
                        "reachability under each is stronger than the question "
                        "-- refused, as NetPlumber refuses it (Q17)" % src)
                key = (src, tuple((f.name, str(f.value), f.negated) for f in cond))
                if self._tracking:
                    self._probes_of.setdefault(key, set()).add(dst)
                if key in keys:
                    continue
                if src not in ir.generators:
                    raise Unsupported("check names unknown source %s" % src)
                _starts, sets = ir.generators[src]
                keys[key] = [s for base in sets
                             for s in self.condition_sets(ir, base, cond)]
                if self._tracking:
                    self._sets_of[key] = keys[key]

        # early exit: the probe tables asked of each key in this call
        early = self.early_exit and not self._tracking
        asked: Dict[Tuple[str, Tuple[Any, ...]], Set[int]] = {}
        if early:
            for dst, checks in rules.items():
                for src, _negated, cond in checks:
                    key = (src, tuple((f.name, str(f.value), f.negated) for f in cond))
                    if dst in ir.probes:
                        asked.setdefault(key, set()).add(ir.probes[dst])
        by_set: Dict[str, List[Tuple[str, Tuple[Any, ...]]]] = {}
        for key, sets in keys.items():
            for qs in sets:
                by_set.setdefault(qs, []).append(key)
        delivered: Dict[Tuple[str, Tuple[Any, ...]], Set[int]] = {k: set() for k in keys}
        witness = self._tracking and 'witness' in self.footprint
        if self._tracking and self.footprint:
            # every set of every key asked is walked below: what was recorded
            # for these keys is replaced, not merged
            for key in keys:
                self._witness[key] = {}
                self._watch.pop(key, None)
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
                walked = self.net.local_deliveries(
                    qs, starts, self.budget, self.revisit == "state", self._scan,
                    self._tracking, witness,
                    [sorted(asked.get(key, ())) for key in owner_of] if early else [],
                    self.state_cache)
                self.early_exits += self.net.last_early_exits
                (answers, finished, stopped_at, predicted, single, local_ecs, hops,
                 per_table) = walked[:8]
                if self._tracking:
                    for key in owners:
                        self._footprints[(key, qs)] = walked[8]
                if witness:
                    # the first path found per (key, delivered table) is its witness
                    for key, per_table_w in zip(owner_of, walked[9]):
                        mine = self._witness[key]
                        for table, w in per_table_w.items():
                            if table not in mine:
                                mine[table] = (w, w.tables())
                self.work.append((owners[0][0], local_ecs, hops))
                if not finished:
                    names = {v: k for k, v in ir.tables.items()}
                    top = sorted(per_table.items(), key=lambda kv: -kv[1])[:3]
                    raise DidNotFinish(owners[0][0], names.get(stopped_at, str(stopped_at)),
                                       predicted, self.budget, single,
                                       [(names.get(t, str(t)), n) for t, n in top])
            for key, tables in zip(owner_of, answers):
                delivered[key].update(tables)
        if self._tracking:
            self._delivered.update(delivered)

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

    # -- incremental updates (INCREMENTAL_PLAN.md §6.2, §6.3) -------------------
    #
    # A rule or link update is applied to the BUILT engine. Which checks it can
    # affect is decided by the walk footprints, not by affected ECs: a check's
    # walk is deterministic, so a rule at table T can change it only if the rule
    # is a candidate at a state the walk reached at T -- the arriving header,
    # after every rewrite on the way -- and a link only if the walk emitted on
    # its port. "The check's set does not meet the rule" would be unsound: a
    # rewrite upstream can carry the set into the rule.

    def takes_updates(self) -> bool:
        return self.ir is not None and self.net is not None

    def _require_built(self, op: str) -> Ir:
        if self.ir is None or self.net is None:
            raise UpdateRefused("VeriFlowAdapter: %s before the model was built" % op)
        if self._rids is None:
            self._rids = {}
            for rid, (node, tname, idx, _port) in self.ir.origin.items():
                self._rids.setdefault((node, tname, idx), []).append(rid)
            self._rule_by_id = {r.id: r for r in self.ir.rules}
            self._next_rid = max(self._rule_by_id, default=0) + 1
        return self.ir

    def _affects(self, hit: Any) -> None:
        """ Mark every source with a query set whose footprint `hit` accepts,
        or which has no footprint yet (unknown is affected). """
        if not self._tracking:
            return
        for key, sets in self._sets_of.items():
            src = key[0]
            if src in self._pending:
                continue
            for qs in sets:
                fp = self._footprints.get((key, qs))
                if fp is None or hit(fp):
                    self._pending.add(src)
                    break

    def _affects_rule(self, rule: IrRule, inserted: bool) -> None:
        """ Mark what a rule update can affect: an insert is judged with the
        rule loaded, a deletion before it is unloaded (its fall-through needs
        it, and the footprint from BEFORE the deletion). """
        if not self._tracking:
            return
        if not self.footprint:
            self._affects(lambda fp: self.net.footprint_hits_rule(
                fp, rule.table, rule.in_port, rule.match))
            return
        net, ir = self.net, self.ir
        assert ir is not None
        witness, dead_ends = 'witness' in self.footprint, 'dead-ends' in self.footprint
        inserted_fate = None
        for key, sets in self._sets_of.items():
            src = key[0]
            if src in self._pending:
                continue
            fps = [self._footprints.get((key, qs)) for qs in sets]
            if any(fp is None for fp in fps):
                self._pending.add(src)            # unknown is affected
                continue
            explored = [fp for fp in fps if net.footprint_hits_rule(
                fp, rule.table, rule.in_port, rule.match)]
            delivered = self._delivered.get(key, set())
            witnesses = self._witness.get(key, {})
            fate = None
            for probe in self._probes_of.get(key, ()):
                pair = (src, probe)
                if pair in self._pending_pairs:
                    continue
                table = ir.probes[probe]
                if witness and table in delivered and table in witnesses:
                    # §4.1: only a rule that moves the witness's packet
                    w, tables = witnesses[table]
                    hit = rule.table in tables and net.witness_hits_rule(
                        w, rule.table, rule.in_port, rule.match, self.witness_point)
                elif not explored:
                    hit = False
                elif dead_ends and table not in delivered:
                    # §4.2: a change that sends the packets nowhere cannot
                    # open a path to this probe
                    if fate is None:
                        if inserted:
                            if inserted_fate is None:
                                inserted_fate = net.rule_fate(rule.id)
                            fate = inserted_fate
                        else:
                            opens, consumed, unlinked = False, set(), set()
                            for fp in explored:
                                o, c, u = net.delete_fate(fp, rule.id)
                                opens, consumed, unlinked = opens or o, consumed | c, unlinked | u
                            fate = (opens, consumed, unlinked)
                    opens, consumed, unlinked = fate
                    hit = opens or table in consumed
                    if not hit and unlinked:
                        self._watch.setdefault(key, {}).setdefault(probe, set()).update(unlinked)
                else:
                    hit = True
                if hit:
                    self._pending_pairs.add(pair)

    def _affects_link(self, port: int, up: bool) -> None:
        """ Mark what a link update on `port` can affect: with a witness a
        delivered pair only by a link going DOWN on its path; with dead ends an
        undelivered one only by a link coming UP on a port its walk emitted on
        or a dead end left unlinked (§4.1, §4.2). """
        if not self._tracking:
            return
        if not self.footprint:
            self._affects(lambda fp: fp.hits_port(port))
            return
        assert self.ir is not None
        witness, dead_ends = 'witness' in self.footprint, 'dead-ends' in self.footprint
        for key, sets in self._sets_of.items():
            src = key[0]
            if src in self._pending:
                continue
            fps = [self._footprints.get((key, qs)) for qs in sets]
            if any(fp is None for fp in fps):
                self._pending.add(src)
                continue
            explored = any(fp.hits_port(port) for fp in fps)
            delivered = self._delivered.get(key, set())
            witnesses = self._witness.get(key, {})
            watch = self._watch.get(key, {})
            for probe in self._probes_of.get(key, ()):
                pair = (src, probe)
                if pair in self._pending_pairs:
                    continue
                table = self.ir.probes[probe]
                if witness and table in delivered and table in witnesses:
                    hit = not up and witnesses[table][0].hits_port(port)
                elif dead_ends and table not in delivered:
                    hit = up and (explored or port in watch.get(probe, ()))
                else:
                    hit = explored or port in watch.get(probe, ())
                if hit:
                    self._pending_pairs.add(pair)

    def insert_rule(self, rule: Any) -> None:
        ir = self._require_built('insert_rule')
        key = (rule.node, rule.tid, rule.idx)
        assert self._rids is not None
        if key in self._rids:
            raise UpdateRefused(
                "VeriFlowAdapter: insert_rule%s: the rule is already present; "
                "a modify is a delete followed by an insert" % (key,))
        if rule.tid not in ir.tables:
            raise UpdateRefused("VeriFlowAdapter: insert_rule%s into a table the "
                                "model does not have" % (key,))
        if rule.tid in self.lpm_declared:
            try:
                priority = self.lpm_priority(rule)     # its band (O1)
            except Unsupported as err:
                raise UpdateRefused("VeriFlowAdapter: insert_rule%s: %s"
                                    % (key, err)) from err
        else:
            priority = self.prio_of.get((rule.tid, rule.idx), -rule.idx)
        try:
            translated = self.translate_rule(ir, rule.tid, rule, priority, self._next_rid)
        except (KeyError, Unsupported) as err:
            raise UpdateRefused(
                "VeriFlowAdapter: insert_rule%s needs a field or port the built "
                "layout does not have (%s); that is a rebuild, not an update"
                % (key, err)) from err
        for ir_rule, _port in translated:
            for (name, width), scan in zip(ir.fields, self._scan):
                bits = ir_rule.match[ir.offset(name):ir.offset(name) + width]
                if scan and 'x' in bits and set(bits) != {'x'}:
                    raise UpdateRefused(
                        "VeriFlowAdapter: insert_rule%s is not exact-or-ANY on "
                        "scan field %s (V3b, D6); that is a rebuild" % (key, name))
        self._updated = True
        self._rids[key] = []
        for ir_rule, port in translated:
            self.net.load_rule(ir_rule.id, ir_rule.table, ir_rule.priority,
                               ir_rule.in_port, ir_rule.match, ir_rule.out_ports,
                               ir_rule.consume, ir_rule.rewrites)
            # after loading: an insert's fate (§4.2) is the loaded rule's; the
            # footprint test does not depend on the network
            self._affects_rule(ir_rule, inserted=True)
            ir.rules.append(ir_rule)
            ir.origin[ir_rule.id] = (rule.node, rule.tid, rule.idx, port)
            self._rule_by_id[ir_rule.id] = ir_rule
            self._rids[key].append(ir_rule.id)
        self._next_rid += len(translated)

    def delete_rule(self, node: str, tid: str, idx: int) -> None:
        ir = self._require_built('delete_rule')
        assert self._rids is not None
        rids = self._rids.pop((node, tid, idx), None)
        if rids is None:
            raise UpdateRefused("VeriFlowAdapter: delete_rule(%s, %s, %s): no such "
                                "rule" % (node, tid, idx))
        self._updated = True
        for rid in rids:
            # judged against the footprint from BEFORE the deletion
            self._affects_rule(self._rule_by_id.pop(rid), inserted=False)
            self.net.unload_rule(rid)
            del ir.origin[rid]
        gone = set(rids)
        ir.rules = [r for r in ir.rules if r.id not in gone]

    def set_link(self, sport: str, dport: str, up: bool) -> None:
        ir = self._require_built('set_link')
        if dport not in ir.ports:
            raise UpdateRefused("VeriFlowAdapter: set_link to unknown port %s" % dport)
        generator = {g.node + ".1": g.node for g in self._generators}.get(sport)
        self._updated = True
        if generator is not None:
            # A link leaving a generator is not an engine link but a start (Q21).
            start = (ir.port_table[ir.ports[dport]], ir.ports[dport])
            starts = ir.generators[generator][0]
            if up:
                starts.append(start)
            elif start in starts:
                starts.remove(start)
            if self._tracking:
                self._pending.add(generator)
            return
        if sport not in ir.ports:
            raise UpdateRefused("VeriFlowAdapter: set_link from unknown port %s" % sport)
        a, b = ir.ports[sport], ir.ports[dport]
        self._affects_link(a, up)
        if up:
            self.net.add_link(a, b)
            ir.links.append((a, b))
        else:
            self.net.remove_link(a, b)
            if (a, b) in ir.links:
                ir.links.remove((a, b))

    def remove_device(self, model: Any, links: List[Tuple[str, str]]) -> None:
        """ INCREMENTAL_PLAN.md §8.2, by EMPTYING (Q-R2; ACCOMMODATIONS.md):
        the device's external links go down -- those INTO it first -- and
        every rule it holds is deleted, through `set_link` and `delete_rule`
        and their footprints. Its tables, ports and internal wiring stay: a
        table without rules sends nothing on, so the device answers as an
        absent one, which the from-zero oracle checks. Adding the same name
        again is refused (`add_tables`). Refused before anything is touched
        unless the model is built and every link is one it knows. """
        ir = self._require_built('remove_device')
        assert self._rids is not None
        starts = {g.node + ".1" for g in self._generators}
        unknown = [(a, b) for a, b in links
                   if b not in ir.ports or (a not in ir.ports and a not in starts)]
        if unknown:
            raise UpdateRefused("VeriFlowAdapter: remove_device(%s): links to "
                                "unknown ports %s" % (model.node, unknown[:3]))
        inbound = [l for l in links if l[1] in model.ports]
        for sport, dport in inbound:
            self._link_down(sport, dport)
        for key in sorted(k for k in self._rids if k[0] == model.node):
            self.delete_rule(*key)
        for sport, dport in [l for l in links if l not in inbound]:
            self._link_down(sport, dport)
        self._emptied.add(model.node)

    def _link_down(self, sport: str, dport: str) -> None:
        """ `set_link(.., up=False)` for a link that is up; one already down
        has nothing left to take. """
        assert self.ir is not None
        ports = self.ir.ports
        if sport in ports and (ports[sport], ports[dport]) not in self.ir.links:
            return
        self.set_link(sport, dport, False)

    def add_tables(self, model: Any) -> None:
        if model.node in self._emptied:
            raise UpdateRefused(
                "VeriFlowAdapter: add_tables(%s): the device was removed by "
                "emptying (INCREMENTAL_PLAN.md §8.2); adding it again is not "
                "implemented" % model.node)
        super().add_tables(model)

    def max_rule_index(self, table: str) -> int:
        """ §8.1: priorities are `-idx`, and in a declared-LPM table
        `plen·2^40 − idx` (O1), so an index stays below 2^40. """
        return 2**40 - 1

    def track_affected(self, on: bool) -> None:
        self._tracking = on
        if not on:
            self._footprints, self._sets_of, self._pending = {}, {}, set()
            self._delivered, self._probes_of, self._witness = {}, {}, {}
            self._watch, self._pending_pairs = {}, set()

    def take_affected(self) -> Optional[Set[Tuple[str, str]]]:
        """ The (source, probe) pairs an update since the last call can affect:
        with the coarse footprint every pair of every source marked -- a
        source's walk delivers to every probe, so a change to it can move any
        of them; with a footprint mode, the pairs marked one by one (§4.3),
        plus every pair of a source with no footprint yet. None (re-verify
        everything) when not tracking, or under network-wide slicing, which
        records no footprint. """
        if not self._tracking or self.slicing != "device" or self.ir is None:
            return None
        self._affects(lambda _fp: False)   # sources with no footprint yet
        pending, self._pending = self._pending, set()
        pairs, self._pending_pairs = self._pending_pairs, set()
        return {(src, probe) for src in pending for probe in self.ir.probes} | pairs

    def clear_results(self) -> None:
        self._results = []

    def stop(self, *_args: Any, **_kwargs: Any) -> None:
        pass
