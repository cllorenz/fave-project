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
import os
import random
import time

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
        #: (line, old, new) for each check the last `selective` changed -- the
        #: count of verdict changes a timed run reports (INCREMENTAL_PLAN.md O3)
        self.last_changes: List[Tuple[str, bool, bool]] = []

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
        fresh = self.ask(todo)
        self.last_changes = [(line, self.verdict[line], now)
                             for line, now in fresh.items()
                             if line in self.verdict and self.verdict[line] != now]
        self.verdict.update(fresh)
        return todo



# --- the shared initialization (INCREMENTAL_PLAN.md D17) ------------------------

def all_rules(checks: Iterable[Check]) -> Dict[str, List[Any]]:
    """ Every check as one `check_compliance` rules dict -- for `prepare`,
    which only needs to know what the checks ask (VeriFlow-FR: the fields
    their conditions name), not which check a verdict belongs to. """
    rules: Dict[str, List[Any]] = {}
    for check in checks:
        rules.setdefault(check.probe, []).append(
            [check.source, check.negated, check.cond])
    return rules


class Phases:
    """ The timed phases of a cell's initialization, in order: name ->
    seconds (`record`). """

    def __init__(self) -> None:
        self.seconds: Dict[str, float] = {}

    def record(self, name: str) -> Any:
        phases = self

        class _Timer:
            def __enter__(self) -> None:
                self.t0 = time.perf_counter()

            def __exit__(self, *_exc: Any) -> None:
                phases.seconds[name] = time.perf_counter() - self.t0
        return _Timer()


def initialize(fave: Any, engine: Any, prefix: str, checks: List[Check],
               files: Optional[Dict[str, str]] = None,
               footprint_pass: bool = True,
               phases: Optional[Phases] = None) -> Tuple[VerdictCache, Phases]:
    """ Initialize the model and verify compliance once, as the from-zero
    measurement and the update stream share them (INCREMENTAL_PLAN.md D17):

    * `t_load_s` -- every modelling element through the aggregator, the
      generators without their links;
    * `t_build_s` -- the generators' links (NetPlumber propagates there) and
      the engine's build of what the first check needs (`prepare`; the lazy
      engines build here);
    * `t_check_s` -- the first compliance check, untracked: the from-zero
      measurement (D17.2);
    * `t_footprint_s` -- with `footprint_pass`, tracking on and the checks
      once more over the same model: the incremental phase's setup. Its
      verdicts must equal the first check's; a difference raises.

    `t_start_s` (the engine's construction) is the caller's: it precedes the
    driver. Returns the verdict cache, holding the first check's verdicts. """
    phases = phases or Phases()
    cache = VerdictCache(fave, engine, checks)
    with phases.record('t_load_s'):
        fave.replay(prefix, files=files, generator_links=False)
    with phases.record('t_build_s'):
        fave.connect_generators()
        fave.prepare(all_rules(checks))
    with phases.record('t_check_s'):
        if checks:
            cache.full()
    if footprint_pass:
        first = dict(cache.verdict)
        with phases.record('t_footprint_s'):
            engine.track_affected(True)
            if checks:
                cache.full()
        if cache.verdict != first:
            differ = sorted(line for line in first if cache.verdict.get(line) != first[line])
            raise RuntimeError("the footprint pass changed %d verdicts of the first "
                               "check, e.g. %s" % (len(differ), differ[:3]))
        engine.take_affected()
    return cache, phases

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
              files: Optional[Dict[str, str]] = None,
              like: Any = None) -> Dict[str, bool]:
    """ Verdicts of a from-zero build of the workload at `prefix` minus the
    `deleted` rules and `down` links, on a fresh engine from `make_engine`.

    Built as the engine under test was: with tracking on from the start, and,
    given that engine as `like`, with the translation choices it fixed at its
    own build (`prepare_twin`) -- for APKeep, the element structure decided
    from the INITIAL model, which an update must not change and which can
    represent a model its default translation refuses. Never an update: the
    oracle stays independent of the path it checks. """
    from util.in_process_driver import InProcessFaVe
    engine = make_engine()
    engine.track_affected(True)
    if like is not None and hasattr(like, 'prepare_twin'):
        like.prepare_twin(engine)
    with InProcessFaVe(_Withholding(engine, set(deleted), set(down))) as fave:
        fave.replay(prefix, files=files)
        verdicts = VerdictCache(fave, engine, checks).full()
    # the oracle's engine is never used again: an engine holding shared state
    # (an NDD-APKeep network) lets go of it
    if hasattr(engine, 'release'):
        engine.release()
    return verdicts


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
          down: Set[Tuple[str, str]],
          refused: Optional[List[Tuple[Update, str]]] = None) -> bool:
    """ Apply one update to a built engine, and keep `deleted`/`down` -- the
    oracle's view of the current model -- in step with it.

    An engine REFUSES an update it cannot take in place, before changing
    anything (APKeep: a new element, an untranslatable model). With `refused`
    given, the refusal is recorded there with its reason and the stream goes
    on -- the model then keeps the rule or link, for the engine and the oracle
    alike; without it, the refusal propagates. Returns whether it applied. """
    if refused is not None:
        from aggregator.abstract_engine import UpdateRefused
        try:
            apply(engine, update, deleted, down)
        except UpdateRefused as err:
            refused.append((update, str(err)))
            return False
        return True
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
    return True


# --- S4: configuration edits through the aggregator (INCREMENTAL_PLAN.md §8.1) --

#: device types whose configuration is a file of rule lines, and how a line of
#: it is recognised as a RULE: iptables appends (`-A`), Cisco ACL entries
_S4_RULE_LINE = {
    'packet_filter': lambda line: ' -A ' in line,
    'host': lambda line: ' -A ' in line,
    'application_layer_gateway': lambda line: ' -A ' in line,
    'router': lambda line: line.startswith('access-list '),
}


#: device types whose rule lines form named lists that the rest of the
#: configuration refers to, and a line's list: a router's ACL number. A delete
#: must leave every list one entry, or an interface's `ip access-group` names
#: an ACL the router model no longer has (the D11 run's wl_ifi S4 cells,
#: KeyError at edit 124). An iptables chain may become empty; it has a policy.
_S4_RULE_LIST = {
    'router': lambda line: line.split()[1],
}


def _config_index(device: List[Any]) -> int:
    """ Where a topology.json device entry keeps its configuration path. """
    return {'packet_filter': 4, 'host': 4, 'application_layer_gateway': 4,
            'router': 3}[device[1]]


def _flip(line: str) -> Optional[str]:
    """ S4's modify: the line with its action inverted; None if it has none
    to invert, or if it is a state-checking iptables rule (an `ESTABLISHED`
    rule's action decides a whole state shell -- a structural edit, not a
    rule edit). """
    if 'ESTABLISHED' in line:
        return None
    for a, b in ((' -j ACCEPT', ' -j DROP'), (' -j DROP', ' -j ACCEPT'),
                 (' permit ', ' deny '), (' deny ', ' permit ')):
        if a in line:
            return line.replace(a, b, 1)
    return None


def _flip_route(entry: List[Any]) -> Optional[List[Any]]:
    """ S4's modify for a switch rule (a routes.json entry): a forwarding rule
    becomes a drop; a drop has nothing to invert. """
    if not entry[4]:
        return None
    return entry[:4] + [[]] + entry[5:]


class S4Configs:
    """ The editable configurations of a workload, edited one rule at a time:
    a working copy of every rule FILE its topology names (`devices` points at
    the copies), and, for a workload of switches (wl_cloud), every switch's
    rule list from routes.json -- a switch's configuration is its table, kept
    in table order and numbered by position when sent, as a generator would. """

    def __init__(self, prefix: str, workdir: str) -> None:
        with open(os.path.join(prefix, 'topology.json')) as raw:
            self.devices = json.load(raw)['devices']
        self.prefix, self.workdir = prefix, workdir
        self.lines: Dict[int, List[Any]] = {}
        for n, device in enumerate(self.devices):
            if device[1] not in _S4_RULE_LINE:
                continue
            i = _config_index(device)
            with open(device[i]) as raw:
                self.lines[n] = raw.read().split('\n')
            device[i] = os.path.join(workdir, 'config_%d' % n)
            self._write(n)
        #: switch device index -> its table, when the workload has no rule files
        self.switches: Dict[int, List[List[Any]]] = {}
        self._routes: List[List[Any]] = []
        if not self.lines and os.path.exists(os.path.join(prefix, 'routes.json')):
            with open(os.path.join(prefix, 'routes.json')) as raw:
                self._routes = json.load(raw)
            index = {d[0]: n for n, d in enumerate(self.devices) if d[1] == 'switch'}
            for entry in self._routes:
                if entry[0] in index:
                    self.switches.setdefault(index[entry[0]], []).append(entry)
            for table in self.switches.values():
                table.sort(key=lambda e: e[2])

    def _write(self, n: int) -> None:
        with open(self.devices[n][_config_index(self.devices[n])], 'w') as out:
            out.write('\n'.join(self.lines[n]))

    def rule_lines(self) -> List[Tuple[int, int]]:
        """ (device, line) of every rule line, in topology then file order. """
        if self.switches:
            return [(n, i) for n in sorted(self.switches)
                    for i in range(len(self.switches[n]))]
        return [(n, i) for n in sorted(self.lines)
                for i, line in enumerate(self.lines[n])
                if _S4_RULE_LINE[self.devices[n][1]](line)]

    def text(self, n: int, i: int) -> Any:
        return self.switches[n][i] if self.switches else self.lines[n][i]

    def deletable(self, n: int, i: int, lines: List[Tuple[int, int]]) -> bool:
        """ Whether deleting rule line `i` of device `n` leaves the device a
        rule, and the line's list (_S4_RULE_LIST) an entry; `lines` is
        rule_lines(). """
        same = [j for d, j in lines if d == n]
        if len(same) < 2:
            return False
        key = None if self.switches else _S4_RULE_LIST.get(self.devices[n][1])
        if key is None:
            return True
        mine = key(self.lines[n][i])
        return sum(1 for j in same if key(self.lines[n][j]) == mine) > 1

    def flip(self, n: int, i: int) -> Any:
        return _flip_route(self.switches[n][i]) if self.switches else _flip(self.lines[n][i])

    def switch_table(self, n: int) -> List[List[Any]]:
        """ A switch's rule list, numbered by position (index 1, 2, ...). """
        return [e[:2] + [k] + e[3:] for k, e in enumerate(self.switches[n], start=1)]

    def resend(self, fave: Any, n: int) -> None:
        """ Send device `n`, as edited, through `fave` (an InProcessFaVe). """
        if self.switches:
            fave.resend_switch(self.devices[n][0], self.switch_table(n))
        else:
            fave.resend_device(self.devices[n])

    def apply(self, edit: Tuple[str, int, int, str]) -> int:
        """ Apply one edit to the working copy; returns its device index. """
        op, n, i, text = edit
        target = self.switches[n] if self.switches else self.lines[n]
        if op == 'insert':
            target.insert(i, text)
        elif op == 'delete':
            del target[i]
        elif op == 'modify':
            target[i] = text
        else:
            raise ValueError("unknown S4 edit %r" % (op,))
        if not self.switches:
            self._write(n)
        return n

    def zero_prefix(self) -> str:
        """ A workload directory of the CURRENT configurations, for a
        from-zero build: the workload's own files, and a topology.json whose
        devices point at the working copies. """
        zero = os.path.join(self.workdir, 'zero')
        os.makedirs(zero, exist_ok=True)
        own = {'topology.json'} | ({'routes.json'} if self.switches else set())
        for name in os.listdir(self.prefix):
            if name not in own and not os.path.exists(os.path.join(zero, name)):
                os.symlink(os.path.abspath(os.path.join(self.prefix, name)),
                           os.path.join(zero, name))
        with open(os.path.join(self.prefix, 'topology.json')) as raw:
            topo = json.load(raw)
        topo['devices'] = self.devices
        with open(os.path.join(zero, 'topology.json'), 'w') as out:
            json.dump(topo, out)
        if self.switches:
            edited = {self.devices[n][0] for n in self.switches}
            routes = [e for e in self._routes if e[0] not in edited]
            for n in sorted(self.switches):
                routes.extend(self.switch_table(n))
            with open(os.path.join(zero, 'routes.json'), 'w') as out:
                json.dump(routes, out)
        return zero


def stream_s4(configs: S4Configs, n: int, seed: int) -> Iterator[Tuple[str, int, int, str]]:
    """ S4: `n` one-line configuration edits, each drawn AFTER the previous one
    was applied (positions shift): insert a copy of a rule line before a rule
    line of the same device, delete a rule line, or invert one's action. A
    delete that would leave a device no rule, or a router ACL no entry, is
    made a modify instead (as a delete of a device's last rule always was).
    Position uniform over all rule lines of the workload. The caller applies
    each edit (`configs.apply`) before drawing the next. """
    rng = random.Random(seed)
    for _ in range(n):
        lines = configs.rule_lines()
        op = rng.choice(('insert', 'delete', 'modify'))
        dev, i = rng.choice(lines)
        if op == 'insert':
            same = [j for d, j in lines if d == dev]
            yield ('insert', dev, i, copy.deepcopy(configs.text(dev, rng.choice(same))))
        elif op == 'delete' and configs.deletable(dev, i, lines):
            yield ('delete', dev, i, '')
        else:
            flipped = configs.flip(dev, i)
            if flipped is None:
                yield ('insert', dev, i, copy.deepcopy(configs.text(dev, i)))
            else:
                yield ('modify', dev, i, flipped)
