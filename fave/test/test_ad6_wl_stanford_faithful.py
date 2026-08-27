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

""" wl_stanford through Ad6Adapter, FAITHFUL VLAN (admission + rewrite) --
AD6_PLAN.md §5.4 Stage B, B2.

Ported (not imported) from apkeep/adapter.py's own P7b Stanford-faithful
capture methods (`_capture_mid_rewrite`/`_capture_out_reset`/
`_capture_in_admission`), onto ad6's OWN mechanism: Stage A's SSA/
frame-axiom mutation encoding for the rewrite side
(`GenUtils.action(..., rewrite_field=, rewrite_value=)`) and Stage A2's
`GenUtils.fieldmatch()` for the match side, instead of APKeep's inline-NAT/
ACLElement transfer functions -- same semantics (§5.4 Stage B: "reuse
APKeep's own faithful-VLAN subset protocol ... for direct comparability"),
different backend.

Unit tests only (fake Rule/RuleField/Forward/Rewrite objects, no ad6
binary/subprocess/benchmark inputs) for the four new Ad6Adapter capture
methods this milestone adds -- opt-in, gated on `faithful_vlan=True`
(every existing plain-mode call site/test, B0/B1 included, is unaffected
by construction: the flag defaults to False). favemodel.py's own
consumption of the resulting IR fields is separately tested ad6-side
(`ad6/test/parser/favemodeltest.py::FaithfulVlanWiringTest`), through a
real Kripke/CNF build -- this file stops at the capture layer, mirroring
`test_ad6_wl_stanford_plain.py`'s own division of labour.
"""

import logging
import unittest

from ad6.adapter import Ad6Adapter
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField

_DST = 'packet.ipv4.destination'
_VLAN = 'packet.ether.vlan'


def _rewrite(field, value):
    return Rewrite(rewrite=[RuleField(field, value)])


def _rule(device, table, idx, dst=None, vlan=None, ports=(), in_ports=(),
          forwards=True, extra_actions=()):
    fields = []
    if dst is not None:
        fields.append(RuleField(_DST, dst))
    if vlan is not None:
        fields.append(RuleField(_VLAN, vlan))
    match = Match(fields)
    actions = list(extra_actions)
    if forwards and ports:
        actions.append(Forward(ports=list(ports)))
    return Rule(device, table, idx, in_ports=list(in_ports), match=match, actions=actions)


class _FakeModel:
    def __init__(self, node, tables):
        self.node = node
        self.tables = tables


class TestAd6StanfordMidRewrite(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B2): `_capture_mid_rewrite` -- direct
    port of apkeep/adapter.py's own. """

    def setUp(self):
        self.engine = Ad6Adapter(
            logging.getLogger("test_stanford_mid_rewrite"), faithful_vlan=True)

    def test_records_dst_port_and_rewritten_vlan(self):
        rule = _rule('mid.dev', 'mid.dev.1', 1, dst='10.0.0.0/24', ports=['mid.dev.2'],
                     extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_mid_rewrite('mid.dev', rule)
        self.assertEqual(
            self.engine._mid_rw['mid.dev'], [('10.0.0.0/24', 'mid.dev.2', '110')])

    def test_no_dst_records_none(self):
        rule = _rule('mid.dev', 'mid.dev.1', 1, ports=['mid.dev.2'],
                     extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_mid_rewrite('mid.dev', rule)
        self.assertEqual(self.engine._mid_rw['mid.dev'], [(None, 'mid.dev.2', '110')])

    def test_no_rewrite_action_is_a_noop(self):
        rule = _rule('mid.dev', 'mid.dev.1', 1, dst='10.0.0.0/24', ports=['mid.dev.2'])
        self.engine._capture_mid_rewrite('mid.dev', rule)
        self.assertEqual(self.engine._mid_rw, {})

    def test_no_forward_action_is_a_noop_even_with_a_rewrite(self):
        """ A rewrite riding on a rule with no real forward (e.g. a drop)
        carries no meaningful egress port to record against -- mirrors
        `_out_ports` returning [] for a non-forwarding rule. """
        rule = _rule('mid.dev', 'mid.dev.1', 1, dst='10.0.0.0/24', ports=[],
                     forwards=False, extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_mid_rewrite('mid.dev', rule)
        self.assertEqual(self.engine._mid_rw, {})

    def test_multi_port_route_records_only_the_first_port(self):
        """ Same simplification as apkeep/adapter.py's own capture (its
        docstring is explicit this is a known, accepted narrowing, not a
        bug) -- kept identical here for direct comparability, not
        "fixed", since a Rewrite applies regardless of which ECMP branch
        fires and real Stanford data has not been observed to combine
        ECMP with a mid-stage VLAN rewrite on the same route. """
        rule = _rule('mid.dev', 'mid.dev.1', 1, dst='10.0.0.0/24',
                     ports=['mid.dev.2', 'mid.dev.3'],
                     extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_mid_rewrite('mid.dev', rule)
        self.assertEqual(
            self.engine._mid_rw['mid.dev'], [('10.0.0.0/24', 'mid.dev.2', '110')])


class TestAd6StanfordOutReset(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B2): `_capture_out_reset` -- direct port
    of apkeep/adapter.py's own. """

    def setUp(self):
        self.engine = Ad6Adapter(
            logging.getLogger("test_stanford_out_reset"), faithful_vlan=True)

    def test_reset_rule_records_in_port_and_source_vlan(self):
        rule = _rule('out.dev', 'out.dev.1', 1, vlan='110', ports=['out.dev.120'],
                     in_ports=['out.dev.130'], extra_actions=[_rewrite(_VLAN, '0')])
        model = _FakeModel('out.dev', {'out.dev.1': [rule]})
        self.engine._capture_out_reset(model)
        self.assertEqual(self.engine._out_reset['out.dev'], {('130', '110')})

    def test_rewrite_to_nonzero_is_not_a_reset(self):
        rule = _rule('out.dev', 'out.dev.1', 1, vlan='110', ports=['out.dev.120'],
                     in_ports=['out.dev.130'], extra_actions=[_rewrite(_VLAN, '5')])
        model = _FakeModel('out.dev', {'out.dev.1': [rule]})
        self.engine._capture_out_reset(model)
        self.assertEqual(self.engine._out_reset['out.dev'], set())

    def test_no_rewrite_at_all_is_not_a_reset(self):
        rule = _rule('out.dev', 'out.dev.1', 1, vlan='110', ports=['out.dev.120'],
                     in_ports=['out.dev.130'])
        model = _FakeModel('out.dev', {'out.dev.1': [rule]})
        self.engine._capture_out_reset(model)
        self.assertEqual(self.engine._out_reset['out.dev'], set())

    def test_no_in_port_is_a_noop(self):
        rule = _rule('out.dev', 'out.dev.1', 1, vlan='110', ports=['out.dev.120'],
                     extra_actions=[_rewrite(_VLAN, '0')])
        model = _FakeModel('out.dev', {'out.dev.1': [rule]})
        self.engine._capture_out_reset(model)
        self.assertEqual(self.engine._out_reset['out.dev'], set())


class TestAd6StanfordInAdmission(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B2): `_capture_in_admission` -- direct
    port of apkeep/adapter.py's own. """

    def setUp(self):
        self.engine = Ad6Adapter(
            logging.getLogger("test_stanford_in_admission"), faithful_vlan=True)

    def test_forwarding_rule_records_its_admitted_vlan(self):
        rule = _rule('in.dev', 'in.dev.1', 1, vlan='10', ports=['in.dev.100000'])
        self.engine._capture_in_admission('in.dev', rule)
        self.assertEqual(self.engine._in_vlans['in.dev'], {'10'})

    def test_multiple_rules_union_into_one_admitted_set(self):
        self.engine._capture_in_admission(
            'in.dev', _rule('in.dev', 'in.dev.1', 1, vlan='10', ports=['in.dev.100000']))
        self.engine._capture_in_admission(
            'in.dev', _rule('in.dev', 'in.dev.1', 2, vlan='20', ports=['in.dev.100000']))
        self.assertEqual(self.engine._in_vlans['in.dev'], {'10', '20'})

    def test_drop_rule_is_not_an_admission(self):
        rule = _rule('in.dev', 'in.dev.1', 1, vlan='10', ports=[], forwards=False)
        self.engine._capture_in_admission('in.dev', rule)
        self.assertEqual(self.engine._in_vlans, {})


class TestAd6StanfordFoldMidRewrites(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B2): `_fold_mid_rewrites` -- ad6-specific
    (APKeep folds this inline inside its own `_build_stanford_faithful`;
    ad6 needs it as its own step since `_collapse_out_stage` already
    discards the out.X stage, and with it the (in_port,vlan) reset
    mapping, before favemodel.py ever sees the IR). """

    def setUp(self):
        self.engine = Ad6Adapter(
            logging.getLogger("test_stanford_fold"), faithful_vlan=True)

    def test_reset_pair_folds_effective_vlan_to_zero(self):
        self.engine._edges = [
            ['mid.r1.110', 'out.r1.130'],   # mid -> out (internal)
            ['out.r1.120', 'in.r2.5'],      # out -> next hop (external)
        ]
        self.engine._mid_rw = {'mid.r1': [('10.0.0.0/24', 'mid.r1.110', '99')]}
        self.engine._out_reset = {'out.r1': {('130', '99')}}
        self.assertEqual(
            self.engine._fold_mid_rewrites(),
            {'mid.r1': [['10.0.0.0/24', 'mid.r1.110', '0']]})

    def test_no_matching_reset_passes_the_mid_vlan_through_unchanged(self):
        self.engine._edges = [
            ['mid.r1.110', 'out.r1.130'],
            ['out.r1.120', 'in.r2.5'],
        ]
        self.engine._mid_rw = {'mid.r1': [(None, 'mid.r1.110', '99')]}
        self.engine._out_reset = {'out.r1': {('130', '5')}}   # a DIFFERENT vlan resets
        self.assertEqual(
            self.engine._fold_mid_rewrites(),
            {'mid.r1': [[None, 'mid.r1.110', '99']]})

    def test_no_out_stage_at_all_passes_through(self):
        """ A mid.X route whose egress port has no internal out.X edge at
        all (e.g. a direct mid.X<->mid.Y link, no out-stage collapse
        involved) -- effective vlan is just the mid-assigned one, no
        reset lookup possible. """
        self.engine._edges = []
        self.engine._mid_rw = {'mid.r1': [(None, 'mid.r1.110', '99')]}
        self.engine._out_reset = {}
        self.assertEqual(
            self.engine._fold_mid_rewrites(),
            {'mid.r1': [[None, 'mid.r1.110', '99']]})


if __name__ == "__main__":
    unittest.main()
