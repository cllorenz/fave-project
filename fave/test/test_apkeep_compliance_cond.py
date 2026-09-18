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

""" A compliance check's CONDITION restricts the question APKeep answers, and
is never silently dropped -- APKEEP_BACKEND.md Sec. 9, "the wl_up state
conditions".

wl_up asks reachability separately for NEW and ESTABLISHED traffic: 3302 of its
11902 checks carry a `related:N` condition, and the `related:0` half is
precisely the set the policy expects NOT to get through (a host may answer an
established connection, not open one). `check_compliance` used to unpack `cond`
out of the (source, negated, cond) triple and never look at it again, which does
not fail -- it answers the UNCONDITIONED question and returns a confident
number: 1651 phantom violations where FaVe+NetPlumber and FaVe+ad6 both report
none.

The end-to-end test below therefore asserts BOTH halves, because either alone
passes for the wrong reason:

  * with the conditions, zero violations -- the conditioned question;
  * with the very same checks stripped of their conditions, exactly the 1651
    violations the old code produced. A condition that bound to nothing would
    also give zero above, and this is what catches it.
"""

import json
import logging
import os
import unittest

from types import SimpleNamespace

from apkeep.adapter import APKeepAdapter, _cond_related, available
from apkeep.lib_ndd import available as ndd_available
from rule.rule_model import Forward, Match, Rule, RuleField
from test.backend_gate import require_or_skip
from util.match_util import OXM_FIELD_TO_MATCH_FIELD

_PREFIX = "bench/wl_up"
_CHECKS = "%s/checks.json" % _PREFIX
_INPUTS = [
    "%s/%s" % (_PREFIX, f) for f in
    ("topology.json", "routes.json", "sources.json", "policies.json")
] + [_CHECKS]

# The `related:0` half of wl_up's conditioned checks: unreachable once the
# condition is honoured, all 1651 reported as violations when it is not.
_PHANTOM_VIOLATIONS = 1651


def _inputs_present():
    return all(os.path.isfile(f) for f in _INPUTS)


def _parse_check(check):
    """ bench/compliance_checker.py's own parser -- the wire shape a real run
    posts to the aggregator. """
    src = dst = None
    negated = False
    cond = []
    for token in check.split():
        if token == '!':
            negated = True
        elif token.startswith('s='):
            src = token[2:]
        elif token.startswith('p='):
            dst = token[2:]
        elif token.startswith('f='):
            field, value = token[2:].split(':')
            cond.append({'name': OXM_FIELD_TO_MATCH_FIELD[field],
                         'value': value, 'negated': False})
    return src, dst, negated, cond


def _rules(keep_conditions):
    """ The real wl_up policy in check_compliance's shape. Conditions stay in
    their JSON wire form, exactly as `bench/compliance_checker.py` posts them:
    the aggregator's own `_handler` is what turns each into a `RuleField`, and
    driving that conversion is part of what this exercises. """
    with open(_CHECKS) as raw:
        checks = json.load(raw)
    rules = {}
    for check in checks:
        src, dst, negated, cond = _parse_check(check)
        rules.setdefault(dst, []).append(
            (src, negated, cond if keep_conditions else []))
    return rules


def _stateful_firewall(engine):
    """ The smallest model a state condition can discriminate on: one terminal
    packet filter that accepts ESTABLISHED traffic and drops everything else.

        source.S -> fw (forward_filter) -> probe.P

    Shaped like wl_tum's fw.tum (`forward_filter_in`/`_accept` wired by L1, no
    physical egress and no routing), which _build_pf_pipeline realises as a
    single FilterElement. """
    log = logging.getLogger("test_apkeep_compliance_cond")
    log.setLevel(logging.WARNING)
    adapter = APKeepAdapter(log, faithful_vlan=False, engine=engine)
    table = 'fw.forward_filter'
    model = SimpleNamespace(node='fw', tables={table: [
        Rule('fw', table, 0, [], Match([RuleField('related', '1')]),
             [Forward(['fw.forward_filter_accept'])]),
        Rule('fw', table, 1, [], Match([]), []),          # no action = drop
    ]})
    adapter.add_tables(model)
    adapter.add_rules(model)
    adapter.add_link("source.S.1", "fw.forward_filter_in")
    adapter.add_link("fw.forward_filter_accept", "probe.P.1")
    adapter.add_generator(SimpleNamespace(node='source.S'))
    adapter.add_probe(SimpleNamespace(node='probe.P'))
    return adapter


class TestConditionsAreHonouredOrRefused(unittest.TestCase):
    """ `_cond_related` never skips: a condition is honoured or it raises. """

    def test_an_unconditioned_check_is_unconstrained(self):
        for empty in (None, []):
            self.assertIsNone(_cond_related(empty, "source.a", "probe.b"))

    def test_related_is_read_from_a_rulefield_and_from_its_json(self):
        for value in ('0', '1'):
            self.assertEqual(
                _cond_related([RuleField('related', value)], "s", "p"), int(value))
            self.assertEqual(
                _cond_related([{'name': 'related', 'value': value}], "s", "p"),
                int(value))

    def test_a_field_the_query_cannot_force_is_refused_not_dropped(self):
        # wl_example emits protocol/port conditions; answering the
        # unconditioned question for them would look like a result.
        with self.assertRaises(ValueError) as raised:
            _cond_related([RuleField('packet.ipv6.proto', '6')], "s", "p")
        self.assertIn("cannot be honoured", str(raised.exception))

    def test_a_malformed_condition_is_refused(self):
        for bad in ([{'value': '1'}],                       # no name
                    [{'name': 'related', 'value': 'yes'}],  # not an integer
                    [{'name': 'related', 'value': '7'}],    # not a single bit
                    [RuleField('related', '1', negated=True)]):
            with self.subTest(cond=bad):
                self.assertRaises(ValueError, _cond_related, bad, "s", "p")

    def test_contradictory_conditions_are_refused(self):
        with self.assertRaises(ValueError) as raised:
            _cond_related([RuleField('related', '0'), RuleField('related', '1')],
                          "s", "p")
        self.assertIn("contradictory", str(raised.exception))


@require_or_skip(available() and ndd_available(),
                 "JPype or the APKeep/NDD jars are unavailable")
class TestBothEnginesForceTheStateBit(unittest.TestCase):
    """ The condition reaches the query on the BDD engine as well as the NDD
    one. wl_up below only exercises NDD (the production default), and the two
    force the bit through different machinery -- `ReachabilityChecker`'s
    arrival test against a `BDDACLWrapper` predicate, versus an NDD `and` on
    field REL -- so neither covers the other. """

    def test_the_state_the_filter_demands_is_the_only_one_that_gets_through(self):
        for engine in ('bdd', 'ndd'):
            with self.subTest(engine=engine):
                adapter = _stateful_firewall(engine)
                seen = {}
                for label, cond in (
                        ("unconditioned", []),
                        ("related:0", [{'name': 'related', 'value': '0'}]),
                        ("related:1", [{'name': 'related', 'value': '1'}])):
                    adapter.clear_results()
                    adapter.check_compliance(
                        {"probe.P": [("source.S", False, cond)]})
                    # a violation of a must-reach check == not reachable
                    seen[label] = not adapter.get_compliance_results()
                self.assertEqual(
                    seen,
                    # NEW traffic is dropped; ESTABLISHED is not; unconditioned
                    # asks whether ANY packet gets through, so it reaches.
                    {"unconditioned": True, "related:0": False, "related:1": True},
                    "engine %s does not discriminate on the state bit" % engine)


@require_or_skip(available() and ndd_available(),
                 "JPype or the APKeep/NDD jars are unavailable")
@require_or_skip(_inputs_present(), "wl_up inputs not present")
class TestWlUpStateConditions(unittest.TestCase):
    """ The real wl_up policy, end to end through the production engine. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_compliance_cond")
        log.setLevel(logging.WARNING)
        cls.engine = APKeepAdapter(log, faithful_vlan=False, engine='ndd')

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            fave.check_compliance(_rules(keep_conditions=True))
            cls.conditioned = list(cls.engine.get_compliance_results())
            cls.engine.clear_results()
            fave.check_compliance(_rules(keep_conditions=False))
            cls.unconditioned = list(cls.engine.get_compliance_results())

    def test_the_conditioned_policy_holds(self):
        self.assertEqual(
            self.conditioned, [],
            "wl_up must report no violations, as FaVe+NetPlumber and FaVe+ad6 do")

    def test_dropping_the_conditions_would_have_reported_phantom_violations(self):
        """ The conditions BIND. Without this the test above would also pass for
        a condition that constrained nothing at all. """
        self.assertEqual(len(self.unconditioned), _PHANTOM_VIOLATIONS)
        # ... and every one of them is a check that carried a condition.
        conditioned_pairs = {
            (src, probe)
            for probe, entries in _rules(keep_conditions=True).items()
            for src, _negated, cond in entries if cond
        }
        self.assertTrue(
            {(s, p) for (s, p, _mr, _c) in self.unconditioned} <= conditioned_pairs)


if __name__ == '__main__':
    unittest.main()
