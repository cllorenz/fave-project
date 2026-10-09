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

""" Incremental re-verification at the engine layer -- INCREMENTAL_PLAN.md M1.

Three pieces, each independent of any one engine:

* `VerdictCache` holds a verdict per compliance check and re-verifies either
  every check or only those whose (source, probe) an engine reports as
  affected (§6.4). A check is a parsed `checks.json` line; its key is the line
  itself, so two checks on one (source, probe) with different conditions stay
  two checks.
* `from_zero` builds the CURRENT model -- the workload minus the rules deleted
  and the links taken down so far -- on a fresh engine, through the same
  aggregator path as any build. It never calls an incremental update, so it is
  independent of the code it checks (§5, the oracle).
* `stream_s1`, `stream_s2`, `stream_s3` produce the update streams of §7 from a
  built workload, with every random choice drawn from a stated seed.

Updates are applied to the adapter directly (`insert_rule`, `delete_rule`,
`set_link`); the aggregator cannot delete (§2).
"""

from __future__ import annotations

import copy
import json
import random

from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple

#: (node, tid, idx) -- a rule's identity across the engine layer (§6.1).
RuleKey = Tuple[str, str, int]

#: A pre/post-routing table is translated as a whole; single-rule updates are
#: refused there (NetPlumberAdapter._refuse_special_table), so streams skip it.
_WHOLE_TABLES = ('.pre_routing', '.post_routing')


# --- checks -------------------------------------------------------------------

class Check:
    """ One compliance check, as `bench/compliance_checker.py` parses it. """

    __slots__ = ('line', 'source', 'probe', 'negated', 'cond')

    def __init__(self, line: str) -> None:
        from bench.compliance_checker import _parse_check
        self.line = line
        self.source, self.probe, self.negated, self.cond = _parse_check(line)

    @property
    def pair(self) -> Tuple[str, str]:
        return (self.source, self.probe)

    def __repr__(self) -> str:
        return "Check(%r)" % self.line


def load_checks(path: str) -> List[Check]:
    with open(path) as raw:
        return [Check(line) for line in json.load(raw)]


def _rounds(checks: Iterable[Check]) -> List[List[Check]]:
    """ Split checks into rounds in which every (source, probe) occurs once.

    An engine reports a violation per (source, probe) -- NetPlumber by node
    ids, with a condition vector rather than the check it came from -- so a
    violation can only be attributed to ONE check if no other check on the
    same pair was asked in the same call. wl_up asks two per pair (NEW and
    ESTABLISHED); everything else asks one, so this is one round there.
    """
    rounds: List[List[Check]] = []
    seen: List[Set[Tuple[str, str]]] = []
    for check in checks:
        for i, pairs in enumerate(seen):
            if check.pair not in pairs:
                pairs.add(check.pair)
                rounds[i].append(check)
                break
        else:
            seen.append({check.pair})
            rounds.append([check])
    return rounds


def violated_pairs(engine: Any) -> Set[Tuple[str, str]]:
    """ The (source, probe) NAMES an engine reports as violated. NetPlumber's
    lib adapter reports node ids; every other adapter reports names. """
    results = engine.get_compliance_results()
    generators = getattr(engine, 'generators', None)
    probes = getattr(engine, 'probes', None)
    if results and isinstance(results[0][0], int) and generators is not None:
        sid = {info[1]: name for name, info in generators.items()}
        pid = {info[1]: name for name, info in probes.items()}
        return {(sid[s], pid[p]) for s, p, _v, _c in results
                if s in sid and p in pid}
    return {(s, p) for s, p, _v, _c in results}


# --- the verdict cache ----------------------------------------------------------

class VerdictCache:
    """ A verdict per check, kept across updates (§6.4).

    `ask` is the one place checks reach the engine, through the driver's
    barrier-guarded `check_compliance`, so a backend that raises is an error
    here and never "no violations".
    """

    def __init__(self, fave: Any, engine: Any, checks: List[Check]) -> None:
        self.fave = fave
        self.engine = engine
        self.checks = checks
        self.verdict: Dict[str, bool] = {}   # check line -> violated
        self.asked = 0                        # checks asked, over the lifetime

    def ask(self, checks: Iterable[Check]) -> Dict[str, bool]:
        """ Ask the engine `checks` now; return check line -> violated. """
        out: Dict[str, bool] = {}
        for round_ in _rounds(checks):
            rules: Dict[str, List[Any]] = {}
            for check in round_:
                rules.setdefault(check.probe, []).append(
                    [check.source, check.negated, check.cond])
            self.engine.clear_results()
            self.fave.check_compliance(rules)
            violated = violated_pairs(self.engine)
            for check in round_:
                out[check.line] = check.pair in violated
            self.asked += len(round_)
        return out

    def full(self) -> Dict[str, bool]:
        """ Re-verify every check and replace the cache. """
        self.verdict = self.ask(self.checks)
        return dict(self.verdict)

    def selective(self, affected: Optional[Set[Tuple[str, str]]]) -> List[Check]:
        """ Re-verify the checks on an affected (source, probe), or every check
        when the engine could not say (`affected is None`). Returns the checks
        re-verified. """
        if affected is None:
            todo = list(self.checks)
        else:
            todo = [c for c in self.checks if c.pair in affected]
        self.verdict.update(self.ask(todo))
        return todo


# --- the from-zero oracle -------------------------------------------------------

class _Withholding:
    """ Wraps an engine and withholds deleted rules and downed links from a
    build. Everything else -- including the attributes the aggregator reads and
    mutates in place (`links`, `asyncore_socks`, `global_port`) -- is the
    wrapped engine's. """

    def __init__(self, engine: Any, deleted: Set[RuleKey],
                 down: Set[Tuple[str, str]]) -> None:
        self.__dict__['_engine'] = engine
        self.__dict__['_deleted'] = deleted
        self.__dict__['_down'] = down

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._engine, name, value)

    def add_rules(self, model: Any) -> None:
        kept = copy.copy(model)
        kept.tables = {
            tid: [r for r in rules
                  if (model.node, tid, r.idx) not in self._deleted]
            for tid, rules in model.tables.items()
        }
        self._engine.add_rules(kept)

    def add_link(self, sport: str, dport: str) -> None:
        if (sport, dport) not in self._down:
            self._engine.add_link(sport, dport)

    def add_links_bulk(self, links: Any, use_dynamic: bool = False) -> None:
        self._engine.add_links_bulk(
            [l for l in links if tuple(l) not in self._down],
            use_dynamic=use_dynamic)


def from_zero(make_engine: Callable[[], Any], prefix: str, checks: List[Check],
              deleted: Set[RuleKey], down: Set[Tuple[str, str]],
              files: Optional[Dict[str, str]] = None) -> Dict[str, bool]:
    """ Verdicts of a from-zero build of the workload at `prefix` minus the
    `deleted` rules and `down` links, on a fresh engine from `make_engine`. """
    from util.in_process_driver import InProcessFaVe
    engine = make_engine()
    with InProcessFaVe(_Withholding(engine, set(deleted), set(down))) as fave:
        fave.replay(prefix, files=files)
        return VerdictCache(fave, engine, checks).full()


# --- the model and the streams --------------------------------------------------

def model_rules(fave: Any) -> List[Tuple[RuleKey, Any]]:
    """ Every rule of the built model that single-rule updates apply to, in
    model order (device, then table, then the table's own order). """
    out: List[Tuple[RuleKey, Any]] = []
    for node in sorted(fave._agg.models):
        model = fave._agg.models[node]
        for tid in sorted(model.tables):
            if tid.endswith(_WHOLE_TABLES):
                continue
            for rule in model.tables[tid]:
                out.append(((node, tid, rule.idx), rule))
    return out


def model_links(fave: Any) -> List[Tuple[str, str]]:
    """ Every link of the built topology, sorted, as the ENGINE was given it:
    `(egress_port(sport), ingress_port(dport))`, the pair the aggregator
    resolves before `add_link` (`aggregator_service._sync_diff`). """
    agg = fave._agg
    return sorted(
        (agg.port_to_model[s].egress_port(s), agg.port_to_model[d].ingress_port(d))
        for s, dsts in agg.links.items() for d in dsts)


#: One update: ('insert', key, rule) | ('delete', key, rule) |
#: ('link_down', (sport, dport), None) | ('link_up', (sport, dport), None).
Update = Tuple[str, Any, Any]


def stream_s1(rules: List[Tuple[RuleKey, Any]]) -> Iterator[Update]:
    """ S1: every rule deleted in reverse model order, then inserted in model
    order. APKeep's sequence (insert all, then delete in reverse) with the two
    halves swapped, because the build is the full model: the insert half is
    exactly APKeep's, from an empty model, and the delete half deletes in
    reverse insertion order, as APKeep does. """
    for key, rule in reversed(rules):
        yield ('delete', key, rule)
    for key, rule in rules:
        yield ('insert', key, rule)


def stream_s2(rules: List[Tuple[RuleKey, Any]], fraction: float,
              seed: int) -> Iterator[Update]:
    """ S2: a random `fraction` of the rules deleted one by one, then
    re-inserted one by one, both in the drawn order (NetPlumber's method). """
    rng = random.Random(seed)
    k = max(1, int(round(fraction * len(rules))))
    drawn = rng.sample(rules, k)
    for key, rule in drawn:
        yield ('delete', key, rule)
    for key, rule in drawn:
        yield ('insert', key, rule)


def stream_s3(links: List[Tuple[str, str]]) -> Iterator[Update]:
    """ S3: each link taken down, then up again, one link at a time. """
    for link in links:
        yield ('link_down', link, None)
        yield ('link_up', link, None)


def apply(engine: Any, update: Update, deleted: Set[RuleKey],
          down: Set[Tuple[str, str]]) -> None:
    """ Apply one update to a built engine, and keep `deleted`/`down` -- the
    oracle's view of the current model -- in step with it. """
    op, what, rule = update
    if op == 'delete':
        engine.delete_rule(*what)
        deleted.add(what)
    elif op == 'insert':
        engine.insert_rule(rule)
        deleted.discard(what)
    elif op == 'link_down':
        engine.set_link(what[0], what[1], False)
        down.add(what)
    elif op == 'link_up':
        engine.set_link(what[0], what[1], True)
        down.discard(what)
    else:
        raise ValueError("unknown update %r" % (op,))
