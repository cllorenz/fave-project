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

""" Per-(ARRIVAL PORT, VLAN) ingress admission through Ad6Adapter --
AD6_PLAN.md §5.5, the wl_i2 root cause.

WHAT WAS WRONG. `_capture_in_admission` recorded only the per-DEVICE UNION
of admitted VLANs (`_in_vlans: {device: {vlans}}`), and favemodel.py
checked that union once, at the device's own already-collapsed dst=None
forwarding entry. That is the real per-(port, VLAN) relation PROJECTED onto
the device, and the projection is not sound in the safe direction: dropping
the port makes the gate strictly WEAKER. It was ported that way
deliberately, mirroring `apkeep/adapter.py`'s own
single-check-at-the-collapsed-junction simplification for cross-backend
comparability (AD6_PLAN.md §5.4 Stage B) -- the mistake was assuming that
choice was merely coarse rather than unsound.

WHAT IT COST, measured on the shipped models rather than argued:

  * the per-port set is strictly narrower than its device's union for
    EVERY admitted port -- 223/223 on wl_i2, 252/252 on wl_stanford (i2
    per-port sets run 1-26 VLANs against device unions of 23-94);
  * on wl_i2, 2,555 of the 2,564 route-crossings a real per-port
    configuration REJECTS passed the projected gate -- 99.6%;
  * which is why ad6 reported `source.chic` reaching salt/seat where
    NetPlumber correctly has the flow die at `in.kans`/`in.hous`
    (AD6_PLAN.md §5.5, "STEP (c) DONE" and "ROOT CAUSE").

The concrete case: `out.chic.220045 -> in.kans.400029` rewrites 2,545
routes to `vlan=10`, and that arrival port admits
{11,20,21,30,31,32,40,60,70} -- not 10. `in.kans` as a device DOES admit 10,
on another port, which is exactly what let it through.

NOT FIXED HERE: `apkeep/adapter.py:_capture_in_admission` still has the
same projection (its `_in_vlans` feeds a different consumer -- APKeep's own
input format, `adapter.py:1257-1328` -- so it is a separate change with its
own encoding semantics). Tracked in TODO.md. Until it lands, an ad6-vs-APKeep
faithful-VLAN comparison on wl_stanford is no longer like-for-like, and the
two models' admission gates differ by construction.

Unit tests only (fake Rule/RuleField/Forward objects, no ad6
binary/subprocess/benchmark inputs), same scope split as
`test_ad6_wl_i2_faithful.py`: this file stops at the capture + IR layer.
favemodel.py's own consumption -- the per-port gate group, `entry_key`
routing into it, and the two fallbacks -- is tested ad6-side through a real
Kripke/CNF build and solve
(`ad6/test/parser/favemodeltest.py::PortScopedAdmissionTest`).
"""

import logging
import sys
import unittest

from ad6.adapter import AD6_ROOT, Ad6Adapter, _ANY_PORT
from rule.rule_model import Forward, Match, Rule, RuleField

_VLAN = 'packet.ether.vlan'


def _admit(device, idx, vlan, in_ports, forwards=True):
    """ One in-stage VLAN-admission rule, shaped exactly as
    `bench/wl_i2/i2-json/routes.json` has them -- a `vlan=N` match, a single
    `fd=` to the device's own internal port, and the ingress port(s) the
    admission is scoped to in the positional `in_ports` field, e.g.
    ["in.atla", 1, 1, ["vlan=1"], ["fd=in.atla.100000"],
     ["in.atla.100028", "in.atla.100007"]]. """
    actions = [Forward(ports=['%s.100000' % device])] if forwards else []
    return Rule(device, '%s.1' % device, idx,
                in_ports=list(in_ports),
                match=Match([RuleField(_VLAN, vlan)]),
                actions=actions)


class _FakeModel:
    def __init__(self, node, tables):
        self.node = node
        self.tables = tables


class TestAd6InAdmissionCapture(unittest.TestCase):
    """ `_capture_in_admission` records the relation, keyed by the BARE port
    number `favemodel.entry_key` is called with (`_split_port`), not the
    full "device.port" string the rule carries. """

    def setUp(self):
        self.engine = Ad6Adapter(
            logging.getLogger("test_in_admission"), faithful_vlan=True)

    def test_an_admission_is_scoped_to_its_own_ingress_port(self):
        self.engine._capture_in_admission(
            'in.dev', _admit('in.dev', 1, '10', ['in.dev.100028']))
        self.assertEqual(self.engine._in_vlans['in.dev'], {'100028': {'10'}})

    def test_a_multi_port_admission_is_recorded_on_every_named_port(self):
        """ i2's very first in-stage rule has two: ["in.atla.100028",
        "in.atla.100007"] -- both wires really do admit vlan 1. """
        self.engine._capture_in_admission(
            'in.dev', _admit('in.dev', 1, '1', ['in.dev.100028', 'in.dev.100007']))
        self.assertEqual(self.engine._in_vlans['in.dev'],
                         {'100028': {'1'}, '100007': {'1'}})

    def test_two_vlans_on_one_port_union_on_that_port(self):
        for idx, vlan in ((1, '10'), (2, '20')):
            self.engine._capture_in_admission(
                'in.dev', _admit('in.dev', idx, vlan, ['in.dev.100028']))
        self.assertEqual(self.engine._in_vlans['in.dev'], {'100028': {'10', '20'}})

    def test_the_same_vlan_on_different_ports_does_not_merge_the_ports(self):
        for idx, (vlan, port) in enumerate((('10', '100028'), ('20', '100007'))):
            self.engine._capture_in_admission(
                'in.dev', _admit('in.dev', idx, vlan, ['in.dev.%s' % port]))
        self.assertEqual(self.engine._in_vlans['in.dev'],
                         {'100028': {'10'}, '100007': {'20'}},
                         "THE regression: the old capture unioned these into "
                         "{'10','20'} for the whole device, which admitted "
                         "vlan 10 arriving on 100007 and vice versa")

    def test_separate_devices_do_not_merge(self):
        self.engine._capture_in_admission(
            'in.a', _admit('in.a', 1, '10', ['in.a.1']))
        self.engine._capture_in_admission(
            'in.b', _admit('in.b', 1, '20', ['in.b.1']))
        self.assertEqual(self.engine._in_vlans,
                         {'in.a': {'1': {'10'}}, 'in.b': {'1': {'20'}}})

    def test_a_drop_rule_is_not_an_admission(self):
        self.engine._capture_in_admission(
            'in.dev', _admit('in.dev', 1, '10', ['in.dev.1'], forwards=False))
        self.assertEqual(self.engine._in_vlans, {})

    def test_a_rule_with_no_vlan_match_records_nothing(self):
        rule = Rule('in.dev', 'in.dev.1', 1, in_ports=['in.dev.1'],
                    match=Match([]), actions=[Forward(ports=['in.dev.100000'])])
        self.engine._capture_in_admission('in.dev', rule)
        self.assertEqual(self.engine._in_vlans, {})

    def test_an_admission_naming_no_port_is_recorded_as_port_agnostic(self):
        """ Such a rule admits its VLAN on EVERY port of the device. Dropping
        it -- or gating only the ports that ARE named -- would turn this
        over-approximation into a false UNSAT, which hides real reachability
        and is strictly worse. favemodel._port_scoped_admission falls the
        whole device back to the device-wide gate when it sees this key.
        Neither shipped benchmark has one (all 2,265 wl_stanford and all 390
        wl_i2 in-stage rules name their ports), so this branch exists to
        define the semantics rather than to serve a workload. """
        self.engine._capture_in_admission('in.dev', _admit('in.dev', 1, '10', []))
        self.assertEqual(self.engine._in_vlans['in.dev'], {_ANY_PORT: {'10'}})

    def test_the_any_port_key_matches_favemodels_own(self):
        """ `fave/ad6/adapter.py` deliberately imports nothing from the ad6
        tree (see its module docstring), so the two constants are pinned
        equal here instead of shared. They key the same dict across the IR
        boundary; a silent divergence would make every port-agnostic
        admission look like a real port named "*". """
        # The ad6 tree is a sibling checkout with its own PYTHONPATH
        # assumptions and is not importable from the fave test tier by
        # default -- same one-off sys.path append test_ad6_i2_measure.py
        # already uses, via the adapter's own AD6_ROOT rather than a second
        # hand-rolled relative path.
        if AD6_ROOT not in sys.path:
            sys.path.append(AD6_ROOT)
        from src.parser import favemodel
        self.assertEqual(_ANY_PORT, favemodel._ANY_PORT)


class TestAd6InAdmissionDispatch(unittest.TestCase):
    """ The capture must fire from `add_rules` for an `in.*` model in
    faithful mode, and not at all in plain mode. """

    @staticmethod
    def _model():
        return _FakeModel('in.atla', {'in.atla.1': [
            _admit('in.atla', 1, '1', ['in.atla.100028', 'in.atla.100007']),
            _admit('in.atla', 2, '1201', ['in.atla.100004']),
        ]})

    def _engine(self, faithful):
        engine = Ad6Adapter(
            logging.getLogger("test_in_admission_dispatch"), faithful_vlan=faithful)
        engine.add_tables(_FakeModel('in.atla', {}))
        engine.add_rules(self._model())
        return engine

    def test_faithful_mode_captures_the_relation(self):
        self.assertEqual(self._engine(True)._in_vlans['in.atla'], {
            '100028': {'1'}, '100007': {'1'}, '100004': {'1201'},
        })

    def test_plain_mode_captures_nothing(self):
        self.assertEqual(self._engine(False)._in_vlans, {})

    def test_an_out_stage_model_does_not_reach_the_in_capture(self):
        engine = Ad6Adapter(
            logging.getLogger("test_in_admission_stage"), faithful_vlan=True)
        engine.add_tables(_FakeModel('out.atla', {}))
        engine.add_rules(_FakeModel('out.atla', {'out.atla.1': [
            _admit('out.atla', 1, '10', ['out.atla.110000']),
        ]}))
        self.assertEqual(engine._in_vlans, {})


class TestAd6InAdmissionIR(unittest.TestCase):
    """ `_build_ir` must publish the relation as
    `ir["in_vlans"] = {device: {port: [vlans]}}` -- JSON-serialisable
    (sorted lists, not sets) and deterministically ordered, since this
    payload is what gets archived alongside a measurement. """

    @staticmethod
    def _engine(faithful):
        engine = Ad6Adapter(
            logging.getLogger("test_in_admission_ir"), faithful_vlan=faithful)
        engine.add_tables(_FakeModel('in.atla', {}))
        engine.add_rules(_FakeModel('in.atla', {'in.atla.1': [
            _admit('in.atla', 1, '20', ['in.atla.100028']),
            _admit('in.atla', 2, '3', ['in.atla.100028']),
            _admit('in.atla', 3, '100', ['in.atla.100007']),
        ]}))
        return engine

    def test_faithful_ir_carries_the_nested_relation(self):
        ir = self._engine(True)._build_ir()
        self.assertEqual(ir["in_vlans"], {'in.atla': {
            '100028': ['3', '20'],     # NUMERIC order, not lexicographic
            '100007': ['100'],
        }})

    def test_the_payload_is_json_serialisable(self):
        import json
        ir = self._engine(True)._build_ir()
        self.assertEqual(json.loads(json.dumps(ir["in_vlans"])), ir["in_vlans"])

    def test_plain_ir_has_no_in_vlans_key_at_all(self):
        """ Byte-for-byte-unchanged plain IR, the same guarantee
        `faithful_vlan`'s other IR fields already give. """
        self.assertNotIn("in_vlans", self._engine(False)._build_ir())

    def test_nothing_emits_the_old_flat_shape_any_more(self):
        """ favemodel._in_vlans_for still READS `{device: [vlans]}`, so an
        archived IR keeps building the encoding it was measured against --
        but the adapter must never produce it, or the fix would be silently
        inert. """
        ir = self._engine(True)._build_ir()
        for device, entry in ir["in_vlans"].items():
            self.assertIsInstance(entry, dict, device)


if __name__ == '__main__':
    unittest.main()
