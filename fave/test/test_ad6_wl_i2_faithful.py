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

""" wl_i2 through Ad6Adapter, FAITHFUL VLAN -- the out-stage egress-VLAN
rewrite (`_capture_out_rewrite`), AD6_PLAN.md §5.5 C4.

WHY THIS IS A SEPARATE MECHANISM FROM `_capture_mid_rewrite`. wl_stanford
and wl_i2 put the per-route VLAN rewrite on DIFFERENT stages, and the two
stages get opposite treatment in `_build_ir`:

  * wl_stanford: `mid.X` is the dst FIB and carries the rewrite; `out.X` is
    a pure in-port -> out-port permutation, which `_build_ir` COLLAPSES
    away (`_collapse_out_stage`), folding its `rw=vlan:0` resets into the
    mid rewrite (`_fold_mid_rewrites`).
  * wl_i2: there is NO `mid` stage at all. `out.X` IS the dst FIB *and*
    carries the rewrite -- measured on the real model, all 77,451 `out.X`
    rules match `ipv4_dst` and carry exactly two actions, `rw=vlan:M` plus
    a single `fd=`. Because no `mid.X` device exists, `_build_ir` does NOT
    collapse the out stage, so the rewrite must attach to `out.X`'s own
    surviving forwarding rules.

So `_capture_mid_rewrite` never fires on i2 (no mid stage) and
`_capture_out_reset` records nothing (i2's out rules carry no VLAN MATCH to
key a reset on) -- before this milestone the 77,451 egress rewrites were
dropped in BOTH plain and faithful mode, which is what made
`faithful_vlan=True` produce an incoherent i2 model (in-stage admission
gating on a VLAN nothing ever assigns) rather than a faithful one. See
AD6_PLAN.md §5.5's WORKLOAD-PARITY FINDING.

Direct counterpart of `apkeep/adapter.py:_capture_out_rewrite` (its own i2
faithful path), for the same cross-backend comparability reason the
Stanford-faithful capture methods were ported rather than reinvented.

Unit tests only (fake Rule/RuleField/Forward/Rewrite objects, no ad6
binary/subprocess/benchmark inputs), same scope split as
`test_ad6_wl_stanford_faithful.py`: this file stops at the capture + IR
layer, and favemodel.py's own consumption of `ir["out_rw"]` is tested
ad6-side through a real Kripke/CNF build and solve
(`ad6/test/parser/favemodeltest.py::FaithfulVlanOutRewriteWiringTest`).
"""

import logging
import unittest

from ad6.adapter import Ad6Adapter
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField

_DST = 'packet.ipv4.destination'
_DST6 = 'packet.ipv6.destination'
_VLAN = 'packet.ether.vlan'


def _rewrite(field, value):
    return Rewrite(rewrite=[RuleField(field, value)])


def _rule(device, table, idx, dst=None, dst_field=_DST, vlan=None, ports=(),
          in_ports=(), forwards=True, extra_actions=()):
    fields = []
    if dst is not None:
        fields.append(RuleField(dst_field, dst))
    if vlan is not None:
        fields.append(RuleField(_VLAN, vlan))
    match = Match(fields)
    actions = list(extra_actions)
    if forwards and ports:
        actions.append(Forward(ports=list(ports)))
    return Rule(device, table, idx, in_ports=list(in_ports), match=match, actions=actions)


def _i2_out_rule(device, idx, dst, port, vlan, in_port=None):
    """ The exact shape every one of wl_i2's 77,451 real `out.X` rules has
    (verified against `bench/wl_i2/i2-json/routes.json`): an `ipv4_dst`
    match and TWO actions, `rw=vlan:M` then a single `fd=`. """
    return _rule(device, device + '.1', idx, dst=dst, ports=[port],
                 in_ports=[in_port] if in_port else [],
                 extra_actions=[_rewrite(_VLAN, vlan)])


class _FakeModel:
    def __init__(self, node, tables):
        self.node = node
        self.tables = tables


class TestAd6I2OutRewrite(unittest.TestCase):
    """ AD6_PLAN.md §5.5 C4: `_capture_out_rewrite` -- the out-stage
    counterpart of `_capture_mid_rewrite`, mirroring
    apkeep/adapter.py's own. """

    def setUp(self):
        self.engine = Ad6Adapter(
            logging.getLogger("test_i2_out_rewrite"), faithful_vlan=True)

    def test_records_dst_port_and_rewritten_vlan(self):
        rule = _i2_out_rule('out.atla', 2, '35.0.0.0/8', 'out.atla.120030', '10')
        self.engine._capture_out_rewrite('out.atla', rule)
        self.assertEqual(
            self.engine._out_rw['out.atla'],
            [('35.0.0.0/8', 'out.atla.120030', '10')])

    def test_rewrite_to_vlan_zero_is_recorded_not_dropped(self):
        """ 41,200 of i2's real out routes rewrite to vlan 0 (the access-port
        untag) -- a falsy-looking value that must NOT be treated as "no
        rewrite". Distinguishing "rewrites to 0" from "does not rewrite" is
        the whole point on this workload: the probe filter accepts vlan=0
        only, so a dropped `rw=vlan:0` and a dropped `rw=vlan:10` fail in
        opposite directions. """
        rule = _i2_out_rule('out.atla', 1, '44.0.0.0/8', 'out.atla.120019', '0')
        self.engine._capture_out_rewrite('out.atla', rule)
        self.assertEqual(
            self.engine._out_rw['out.atla'],
            [('44.0.0.0/8', 'out.atla.120019', '0')])

    def test_ipv6_dst_match_is_recognised(self):
        """ i2 itself is IPv4-only, but `_translate_fwd_rule` keys its own
        route on EITHER dst field (`_DSTS`), so a capture that only looked
        at the IPv4 one would silently record `dst=None` and never match
        the route it belongs to. """
        rule = _rule('out.dev', 'out.dev.1', 1, dst='2001:db8::/32',
                     dst_field=_DST6, ports=['out.dev.2'],
                     extra_actions=[_rewrite(_VLAN, '7')])
        self.engine._capture_out_rewrite('out.dev', rule)
        self.assertEqual(
            self.engine._out_rw['out.dev'], [('2001:db8::/32', 'out.dev.2', '7')])

    def test_no_dst_records_none(self):
        rule = _rule('out.dev', 'out.dev.1', 1, ports=['out.dev.2'],
                     extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_out_rewrite('out.dev', rule)
        self.assertEqual(self.engine._out_rw['out.dev'], [(None, 'out.dev.2', '110')])

    def test_no_rewrite_action_is_a_noop(self):
        rule = _rule('out.dev', 'out.dev.1', 1, dst='10.0.0.0/24', ports=['out.dev.2'])
        self.engine._capture_out_rewrite('out.dev', rule)
        self.assertEqual(self.engine._out_rw, {})

    def test_non_vlan_rewrite_is_a_noop(self):
        """ A rule rewriting some OTHER field (e.g. a router's `out_port`
        Rewrite, which `_out_ports` itself reads) is not a VLAN rewrite. """
        rule = _rule('out.dev', 'out.dev.1', 1, dst='10.0.0.0/24', ports=['out.dev.2'],
                     extra_actions=[_rewrite('out_port', 'out.dev.2_egress')])
        self.engine._capture_out_rewrite('out.dev', rule)
        self.assertEqual(self.engine._out_rw, {})

    def test_no_forward_action_is_a_noop_even_with_a_rewrite(self):
        """ A rewrite riding on a rule with no real forward (a drop) has no
        egress port to record against -- mirrors `_out_ports` returning []
        and `_capture_mid_rewrite`'s own guard. """
        rule = _rule('out.dev', 'out.dev.1', 1, dst='10.0.0.0/24', ports=[],
                     forwards=False, extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_out_rewrite('out.dev', rule)
        self.assertEqual(self.engine._out_rw, {})

    def test_multi_port_route_records_only_the_first_port(self):
        """ The same accepted narrowing `_capture_mid_rewrite` documents (a
        Rewrite applies to the packet regardless of which ECMP branch
        fires). Never exercised by real i2 data -- all 77,451 out rules
        carry exactly one `fd=` -- but kept identical to both
        `_capture_mid_rewrite` and apkeep's own capture rather than
        diverging silently. """
        rule = _rule('out.dev', 'out.dev.1', 1, dst='10.0.0.0/24',
                     ports=['out.dev.2', 'out.dev.3'],
                     extra_actions=[_rewrite(_VLAN, '110')])
        self.engine._capture_out_rewrite('out.dev', rule)
        self.assertEqual(self.engine._out_rw['out.dev'], [('10.0.0.0/24', 'out.dev.2', '110')])

    def test_several_routes_on_one_device_accumulate_in_order(self):
        for idx, (dst, port, vlan) in enumerate((
                ('44.0.0.0/8', 'out.atla.120019', '0'),
                ('35.0.0.0/8', 'out.atla.120030', '10'),
                ('18.0.0.0/8', 'out.atla.120030', '10'))):
            self.engine._capture_out_rewrite(
                'out.atla', _i2_out_rule('out.atla', idx, dst, port, vlan))
        self.assertEqual(self.engine._out_rw['out.atla'], [
            ('44.0.0.0/8', 'out.atla.120019', '0'),
            ('35.0.0.0/8', 'out.atla.120030', '10'),
            ('18.0.0.0/8', 'out.atla.120030', '10'),
        ])

    def test_separate_devices_do_not_merge(self):
        """ Same discipline as AD6_PLAN.md §5.4 Stage 0's per-device ACL
        keying: i2 has 9 independent `out.X` devices that reuse the same
        VLAN numbers for unrelated routes. """
        self.engine._capture_out_rewrite(
            'out.atla', _i2_out_rule('out.atla', 1, '35.0.0.0/8', 'out.atla.120030', '10'))
        self.engine._capture_out_rewrite(
            'out.chic', _i2_out_rule('out.chic', 1, '35.0.0.0/8', 'out.chic.220030', '10'))
        self.assertEqual(sorted(self.engine._out_rw), ['out.atla', 'out.chic'])
        self.assertEqual(
            self.engine._out_rw['out.chic'], [('35.0.0.0/8', 'out.chic.220030', '10')])


class TestAd6I2OutRewriteDispatch(unittest.TestCase):
    """ `add_rules` must route an `out.X` forwarding table's rules into
    `_capture_out_rewrite` -- and only when `faithful_vlan` is on. """

    @staticmethod
    def _engine(faithful):
        return Ad6Adapter(
            logging.getLogger("test_i2_out_dispatch"), faithful_vlan=faithful)

    @staticmethod
    def _out_model():
        return _FakeModel('out.atla', {'out.atla.1': [
            _i2_out_rule('out.atla', 1, '44.0.0.0/8', 'out.atla.120019', '0',
                         in_port='out.atla.110000'),
            _i2_out_rule('out.atla', 2, '35.0.0.0/8', 'out.atla.120030', '10',
                         in_port='out.atla.110000'),
        ]})

    def test_faithful_mode_captures_the_out_stage_rewrites(self):
        engine = self._engine(True)
        engine.add_rules(self._out_model())
        self.assertEqual(engine._out_rw['out.atla'], [
            ('44.0.0.0/8', 'out.atla.120019', '0'),
            ('35.0.0.0/8', 'out.atla.120030', '10'),
        ])

    def test_plain_mode_captures_nothing(self):
        engine = self._engine(False)
        engine.add_rules(self._out_model())
        self.assertEqual(engine._out_rw, {})

    def test_the_routes_themselves_are_translated_either_way(self):
        """ The rewrite capture is purely additive: an out.X rule's own
        dst-FIB route must land in `_fwd_rules` identically in both modes,
        so plain-mode i2 measurements stay comparable with the recorded
        ones (`bench/wl_i2/eval/ad6_i2_*.json`). """
        plain, faithful = self._engine(False), self._engine(True)
        plain.add_rules(self._out_model())
        faithful.add_rules(self._out_model())
        self.assertEqual(plain._fwd_rules, faithful._fwd_rules)
        self.assertEqual([r["dst"] for r in plain._fwd_rules],
                         ['44.0.0.0/8', '35.0.0.0/8'])

    def test_a_mid_stage_model_does_not_reach_the_out_capture(self):
        """ Guards the stage dispatch itself: `mid.X` rules keep going to
        `_capture_mid_rewrite` only, so wl_stanford's IR is untouched. """
        engine = self._engine(True)
        engine.add_rules(_FakeModel('mid.r', {'mid.r.1': [
            _rule('mid.r', 'mid.r.1', 1, dst='10.0.0.0/24', ports=['mid.r.2'],
                  extra_actions=[_rewrite(_VLAN, '110')]),
        ]}))
        self.assertEqual(engine._out_rw, {})
        self.assertEqual(engine._mid_rw['mid.r'], [('10.0.0.0/24', 'mid.r.2', '110')])


class TestAd6I2OutRewriteIR(unittest.TestCase):
    """ `_build_ir` must publish the captured rewrites as `ir["out_rw"]`,
    gated on faithful mode and scoped to the devices that actually SURVIVE
    the build -- see the module docstring on why wl_stanford's out stage
    must not contribute. """

    @staticmethod
    def _engine(faithful):
        engine = Ad6Adapter(
            logging.getLogger("test_i2_out_ir"), faithful_vlan=faithful)
        engine.add_tables(_FakeModel('in.atla', {}))
        engine.add_tables(_FakeModel('out.atla', {}))
        engine.add_rules(_FakeModel('out.atla', {'out.atla.1': [
            _i2_out_rule('out.atla', 1, '35.0.0.0/8', 'out.atla.120030', '10',
                         in_port='out.atla.110000'),
        ]}))
        return engine

    def test_faithful_ir_carries_out_rw_as_json_lists(self):
        ir = self._engine(True)._build_ir()
        self.assertEqual(ir["out_rw"], {'out.atla': [['35.0.0.0/8', 'out.atla.120030', '10']]})

    def test_plain_ir_has_no_out_rw_key_at_all(self):
        """ Byte-for-byte-unchanged plain IR, the same guarantee
        `faithful_vlan`'s other IR fields already give. """
        self.assertNotIn("out_rw", self._engine(False)._build_ir())

    def test_a_collapsed_out_stage_contributes_nothing(self):
        """ wl_stanford: a `mid.X` device exists, so `_build_ir` collapses
        the whole `out.*` stage out of `ir["devices"]` and folds its
        `rw=vlan:0` resets into `mid_rw` (`_fold_mid_rewrites`) instead.
        Publishing those same out-stage rewrites AGAIN under `out_rw` would
        be double-counting a rewrite that no surviving device carries -- and
        favemodel.py keys the lookup by device, so the entries would be
        silently inert rather than loudly wrong. Scoped out here explicitly
        rather than relying on that. """
        engine = Ad6Adapter(
            logging.getLogger("test_i2_out_ir_collapse"), faithful_vlan=True)
        for node in ('in.r', 'mid.r', 'out.r'):
            engine.add_tables(_FakeModel(node, {}))
        engine.add_rules(_FakeModel('out.r', {'out.r.1': [
            _rule('out.r', 'out.r.1', 1, vlan='110', ports=['out.r.5'],
                  in_ports=['out.r.3'], extra_actions=[_rewrite(_VLAN, '0')]),
        ]}))
        ir = engine._build_ir()
        self.assertNotIn('out.r', ir["devices"])
        self.assertEqual(ir["out_rw"], {})


if __name__ == '__main__':
    unittest.main()


class _FakeProbe:
    """ The shape `ProbeModel` presents to `add_probe`: wl_i2 declares its
    probes' `vlan=0` in `test_fields` (the condition the probe TESTS on
    arriving flows), not `filter_fields` (which flows it considers at all) --
    verified by instrumenting a real `InProcessFaVe.replay` of
    `bench/wl_i2/i2-json`, where `filter_fields` and `match` are both
    empty. """

    def __init__(self, node, test_fields=None, filter_fields=None, match=()):
        self.node = node
        self.type = 'probe'
        self.quantor = 'existential'
        self.match = list(match)
        self.test_fields = test_fields or {}
        self.filter_fields = filter_fields or {}


def _vlan_test(value):
    return {_VLAN: [RuleField(_VLAN, value)]}


class TestAd6I2ProbeUntagCapture(unittest.TestCase):
    """ AD6_PLAN.md §5.5 C4 (part 2): `add_probe` must record the probe's
    declared arrival VLAN, which it previously dropped on the floor
    (recording only `node + '.1'`). """

    @staticmethod
    def _engine(faithful=True, untag=False):
        return Ad6Adapter(logging.getLogger("test_i2_probe_untag"),
                          faithful_vlan=faithful, probe_untag=untag)

    def test_records_the_probes_test_field_vlan(self):
        engine = self._engine()
        engine.add_probe(_FakeProbe('probe.atla', test_fields=_vlan_test('0')))
        self.assertEqual(engine._probe_vlan, {'probe.atla': '0'})

    def test_still_records_the_probes_port_as_before(self):
        """ Purely additive: the existing `_probes` mapping is untouched. """
        engine = self._engine()
        engine.add_probe(_FakeProbe('probe.atla', test_fields=_vlan_test('0')))
        self.assertEqual(engine._probes, {'probe.atla': 'probe.atla.1'})

    def test_a_non_zero_declared_vlan_is_recorded_verbatim(self):
        engine = self._engine()
        engine.add_probe(_FakeProbe('probe.x', test_fields=_vlan_test('4095')))
        self.assertEqual(engine._probe_vlan, {'probe.x': '4095'})

    def test_a_probe_with_no_vlan_test_field_records_nothing(self):
        """ wl_ifi/wl_up probes (and any probe testing some other field). """
        engine = self._engine()
        engine.add_probe(_FakeProbe('probe.p'))
        engine.add_probe(_FakeProbe(
            'probe.q', test_fields={_DST: [RuleField(_DST, '10.0.0.0/8')]}))
        self.assertEqual(engine._probe_vlan, {})

    def test_a_filter_field_vlan_is_not_a_test_field(self):
        """ The two are different mechanisms and only `test_fields` states
        the arrival condition -- reading `filter_fields` instead would have
        recorded nothing at all on the real i2 model (it is empty there),
        which is the silent-no-op class this integration keeps hitting. """
        engine = self._engine()
        engine.add_probe(_FakeProbe('probe.p', filter_fields=_vlan_test('0')))
        self.assertEqual(engine._probe_vlan, {})

    def test_several_probes_are_kept_separate(self):
        engine = self._engine()
        for name, vlan in (('probe.atla', '0'), ('probe.chic', '0')):
            engine.add_probe(_FakeProbe(name, test_fields=_vlan_test(vlan)))
        self.assertEqual(engine._probe_vlan,
                         {'probe.atla': '0', 'probe.chic': '0'})


class TestAd6I2ProbeUntagIR(unittest.TestCase):
    """ The IR always REPORTS what the model declares (`probe_vlan`); a
    separate, default-off flag decides whether it is ENFORCED
    (`probe_untag`). See AD6_PLAN.md §5.5's PROBE-UNTAG PARITY FINDING for
    why enforcement is not the default: NetPlumber computes this same
    condition and discards it (`netplumber/adapter.py:1008-1056`, two `XXX:
    deactivate ... memory explosion` guards, so it sends `test={"type":
    "true"}` with an empty match), and `apkeep/adapter.py` passes
    `target_vlan=None` for i2 -- so enforcing it here unconditionally would
    make ad6 the strictest of the three and break like-for-like parity in
    the opposite direction from the gap C4 set out to close. """

    @staticmethod
    def _engine(faithful=True, untag=False):
        engine = Ad6Adapter(logging.getLogger("test_i2_probe_untag_ir"),
                            faithful_vlan=faithful, probe_untag=untag)
        engine.add_tables(_FakeModel('out.atla', {}))
        engine.add_probe(_FakeProbe('probe.atla', test_fields=_vlan_test('0')))
        return engine

    def test_faithful_ir_reports_the_declared_probe_vlan(self):
        self.assertEqual(self._engine()._build_ir()["probe_vlan"],
                         {'probe.atla': '0'})

    def test_probe_untag_is_absent_by_default(self):
        self.assertNotIn("probe_untag", self._engine()._build_ir())

    def test_probe_untag_is_emitted_when_opted_in(self):
        self.assertIs(self._engine(untag=True)._build_ir()["probe_untag"], True)

    def test_plain_ir_has_neither_key(self):
        ir = self._engine(faithful=False, untag=True)._build_ir()
        self.assertNotIn("probe_vlan", ir)
        self.assertNotIn("probe_untag", ir)

    def test_the_flag_defaults_off_on_the_constructor(self):
        """ Every existing caller -- `bench/ad6_i2_measure.py`, all the
        wl_ifi/wl_up/wl_stanford tests -- constructs `Ad6Adapter` without
        it and must be unaffected. """
        engine = Ad6Adapter(logging.getLogger("test_i2_probe_untag_default"))
        self.assertIs(engine._probe_untag, False)
        engine_faithful = Ad6Adapter(
            logging.getLogger("test_i2_probe_untag_default2"), faithful_vlan=True)
        self.assertIs(engine_faithful._probe_untag, False)
