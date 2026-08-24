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

""" wl_stanford through Ad6Adapter, PLAIN (no VLAN modelling at all) --
AD6_PLAN.md §5.4 Stage B, B0.

No wl_stanford<->ad6 translator existed before this. Unlike wl_ifi/wl_up
(Cisco-ACL router / ip6tables ruleset shapes), wl_stanford's devices are
`SwitchModel`s named `in.<router>`/`mid.<router>`/`out.<router>` (48 = 16
routers x 3 stages), each with exactly one table `"<device>.1"`. B0 proves
out the PLAIN target only (LPM forwarding + a binary per-physical-port
dead-ingress gate -- no VLAN admission, no VLAN rewrite): the oracle this
must match is NetPlumber==APKeep==165 reachable pairs on the full 16-router
model (`[[stanford-forwarding-overapprox]]`); this file's differential test
checks a small induced 2-router slice (`bbra_rtr,rozb_rtr` -- the same one
`fave/bench/apkeep_convergence.py`'s own faithful-VLAN measurement uses)
against a LIVE NetPlumber worker, not a recorded snapshot -- the full
16-router differential is §5.4 Stage B1, not this file.

Two layers:
  - Unit tests (fake Rule/RuleField/Forward/Rewrite objects, no ad6
    binary/subprocess/benchmark inputs) for the two new Ad6Adapter
    mechanisms this benchmark's real data actually needs:
    `_out_ports`'s multi-port (ECMP) fix and blackhole/discard handling,
    and `_capture_in_admit`'s port-admission tracking.
  - A structural + differential test on the real N=2 slice, reusing
    `fave/bench/apkeep_convergence.py`'s own model-filtering/worker
    machinery for a true apples-to-apples comparison.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest

from ad6.adapter import Ad6Adapter, available
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField
from test.backend_gate import require_or_skip

_DST = 'packet.ipv4.destination'
_VLAN = 'packet.ether.vlan'

_STANFORD_DIR = os.path.join("bench", "wl_stanford", "stanford-json")
_STANFORD_FILES = ("device_topology.json", "routes.json", "probes.json", "sources.json")


def _inputs_present():
    return all(os.path.isfile(os.path.join(_STANFORD_DIR, f)) for f in _STANFORD_FILES)


def _fwd_rule(idx, dst=None, ports=(), in_ports=()):
    match = Match([RuleField(_DST, dst)]) if dst is not None else Match([])
    actions = [Forward(ports=list(ports))] if ports else []
    return Rule('dev', 'mid.dev.1', idx, in_ports=list(in_ports), match=match, actions=actions)


class TestAd6StanfordOutPorts(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B0), Finding 1: `_out_ports` must return
    EVERY port of a multi-port Forward (real wl_stanford mid.* ECMP
    routes, e.g. one dst forwarding to 15 ports at once), not just the
    first -- the old singular `_out_port` silently kept only
    `action.ports[0]`. """

    def setUp(self):
        self.engine = Ad6Adapter(logging.getLogger("test_stanford_out_ports"))

    def test_multi_port_forward_returns_all_ports(self):
        rule = _fwd_rule(1, dst='10.0.0.0/24', ports=['mid.dev.1', 'mid.dev.2', 'mid.dev.3'])
        self.assertEqual(
            self.engine._out_ports(rule), ['mid.dev.1', 'mid.dev.2', 'mid.dev.3'])

    def test_single_port_forward_still_works(self):
        rule = _fwd_rule(1, dst='10.0.0.0/24', ports=['mid.dev.1'])
        self.assertEqual(self.engine._out_ports(rule), ['mid.dev.1'])
        # the singular convenience wrapper other call sites rely on
        self.assertEqual(self.engine._out_port(rule), 'mid.dev.1')

    def test_translate_fwd_rule_records_one_entry_with_all_ports(self):
        """ A multi-port route must be ONE _fwd_rules entry carrying the
        whole port list -- NOT one entry per port, which ad6's sequential
        first-match table evaluation would reduce to "only the first port
        ever reachable" (see fave_ad6/adapter.py::_add_fwd_route and
        ad6/src/parser/favemodel.py::wire_fanout). """
        rule = _fwd_rule(1, dst='10.0.0.0/24', ports=['mid.dev.1', 'mid.dev.2'])
        self.engine._translate_fwd_rule('mid.dev', rule)
        self.assertEqual(len(self.engine._fwd_rules), 1)
        self.assertEqual(self.engine._fwd_rules[0]["ports"], ['mid.dev.1', 'mid.dev.2'])

    def test_dst_only_discard_becomes_a_blackhole(self):
        """ A dst-qualified rule with NO forward action (e.g. wl_stanford's
        real dst=224.0.0.0/3 multicast discard) must become an explicit
        drop, not silently vanish -- a silent no-op would let a broader
        less-specific route (e.g. a /0 default on the same device) wrongly
        claim that traffic instead (an over-approximation). """
        rule = _fwd_rule(1, dst='224.0.0.0/3', ports=[])
        self.engine._translate_fwd_rule('mid.dev', rule)
        self.assertEqual(len(self.engine._fwd_rules), 1)
        self.assertEqual(self.engine._fwd_rules[0]["ports"], ["__drop__"])
        self.assertEqual(self.engine._fwd_rules[0]["dst"], '224.0.0.0/3')

    def test_discard_qualified_by_unsupported_field_is_not_modelled(self):
        """ Soundness guard (mirrors apkeep/adapter.py's own): a discard
        qualified by something other than dst/vlan can't be expressed as a
        dst-only drop without over-dropping traffic that discard never
        actually applies to -- must stay a silent no-op, same as before
        this fix (wl_ifi's existing, unaffected behaviour). """
        match = Match([RuleField(_DST, '224.0.0.0/3'),
                       RuleField('packet.ipv4.source', '10.0.0.0/8')])
        rule = Rule('dev', 'mid.dev.1', 1, match=match, actions=[])
        self.engine._translate_fwd_rule('mid.dev', rule)
        self.assertEqual(self.engine._fwd_rules, [])

    def test_no_dst_no_forward_discard_is_a_noop(self):
        """ A match-all discard (no dst at all) needs no rule -- unmatched
        space is already un-forwarded; unaffected wl_ifi behaviour. """
        rule = Rule('dev', 'mid.dev.1', 1, match=Match([]), actions=[])
        self.engine._translate_fwd_rule('mid.dev', rule)
        self.assertEqual(self.engine._fwd_rules, [])

    def test_repeated_identical_route_is_deduped(self):
        """ wl_stanford's in.* stage: every per-VLAN admission rule shares
        one identical unconditional default route to the device's fixed
        internal egress port -- without dedup, one entry would be added
        per admitted VLAN (harmless but wasteful Kripke-node bloat). """
        rule = _fwd_rule(1, dst=None, ports=['in.dev.100000'])
        for _ in range(5):
            self.engine._translate_fwd_rule('in.dev', _fwd_rule(
                1, dst=None, ports=['in.dev.100000']))
        self.assertEqual(len(self.engine._fwd_rules), 1)


class TestAd6StanfordInAdmit(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B0): `_capture_in_admit` (direct port of
    apkeep/adapter.py's own) -- the union of admitted physical ingress
    ports per `in.*` device, VLAN ignored entirely (B0 has no VLAN
    modelling at all). """

    def setUp(self):
        self.engine = Ad6Adapter(logging.getLogger("test_stanford_in_admit"))

    def test_admitted_ports_accumulate_across_rules(self):
        self.engine._capture_in_admit(
            'in.dev', _fwd_rule(1, ports=['in.dev.100000'], in_ports=['in.dev.1']))
        self.engine._capture_in_admit(
            'in.dev', _fwd_rule(2, ports=['in.dev.100000'], in_ports=['in.dev.2']))
        self.assertEqual(self.engine._in_admit['in.dev'], {'1', '2'})

    def test_rule_with_no_in_port_marks_admit_all(self):
        self.engine._capture_in_admit(
            'in.dev', _fwd_rule(1, ports=['in.dev.100000'], in_ports=['in.dev.1']))
        self.engine._capture_in_admit(
            'in.dev', _fwd_rule(2, ports=['in.dev.100000'], in_ports=[]))
        self.assertIsNone(self.engine._in_admit['in.dev'])
        # once None (admit-all), a later rule must not resurrect a finite set
        self.engine._capture_in_admit(
            'in.dev', _fwd_rule(3, ports=['in.dev.100000'], in_ports=['in.dev.3']))
        self.assertIsNone(self.engine._in_admit['in.dev'])


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_stanford inputs not generated (run test/gen_wl_stanford_inputs.sh)")
class TestAd6WlStanfordPlainN2(unittest.TestCase):
    """ Structural + differential check on the real N=2 induced slice
    (`bbra_rtr,rozb_rtr` -- the same subset
    `fave/bench/apkeep_convergence.py`'s own faithful-VLAN measurement
    uses), against a LIVE NetPlumber worker (not a recorded snapshot --
    same discipline as `fave/test/test_apkeep_stanford.py`, and as §5.4
    Stage B1's own full-scale plan). CAVEAT (from
    `apkeep_convergence.py`'s own module docstring): an induced subnetwork
    poses a NEW, self-contained forwarding problem -- it does not have to
    reproduce the full 16-router model's per-pair verdict, only agree
    with NetPlumber on ITS OWN (smaller) verdict. """

    _ROUTERS = {"bbra_rtr", "rozb_rtr"}

    @classmethod
    def setUpClass(cls):
        from bench.apkeep_convergence import (
            _FILES, _base, _filter_model, _load_model, _write_model, _emit_worker,
        )
        from util.in_process_driver import InProcessFaVe

        model = _filter_model(_load_model(), cls._ROUTERS)
        cls._tmp = tempfile.TemporaryDirectory(prefix="ad6_stanford_n2_")
        _write_model(model, cls._tmp.name)

        log = logging.getLogger("test_ad6_wl_stanford_plain_n2")
        log.setLevel(logging.WARNING)
        cls.engine = Ad6Adapter(log)
        with InProcessFaVe(cls.engine) as fave:
            fave.replay(cls._tmp.name, files=_FILES)
            sources = sorted(cls.engine._generators)
            probes = sorted(cls.engine._probes)
            rules = {p: [[s, False, []] for s in sources] for p in probes}
            fave.check_compliance(rules)

        not_reached = {(s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()}
        cls.ad6_matrix = {
            _base(p): sorted(
                _base(s) for s in sources
                if (s, p) not in not_reached and _base(s) != _base(p)
            )
            for p in probes
        }

        with tempfile.TemporaryDirectory(prefix="ad6_stanford_n2_np_") as np_tmp:
            cls.np_matrix = _emit_worker(
                "netplumber", cls._ROUTERS, os.path.join(np_tmp, "np.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_out_stage_collapsed(self):
        """ B0 has no VLAN modelling at all, so `out.*` must be entirely
        collapsed away in the built IR -- 2 routers x (in,mid) = 4 devices,
        mirroring `test_apkeep_stanford.py::test_out_stage_collapsed`'s own
        structural assertion. `engine._devices` itself still holds every
        raw device `add_tables` ever saw (including `out.*`) -- the
        collapse happens in `_build_ir`, not at capture time (mirrors
        `apkeep/adapter.py`'s own `_build`-time, not capture-time, drop). """
        self.assertIn('out.bbra_rtr', self.engine._devices)
        ir = self.engine._build_ir()
        stages = {d.split('.', 1)[0] for d in ir["devices"]}
        self.assertEqual(stages, {'in', 'mid'})
        self.assertEqual(len(ir["devices"]), 4)

    def test_reachability_matches_netplumber_on_the_induced_slice(self):
        def pairs(matrix):
            return {(s, p) for p, srcs in matrix.items() for s in srcs}

        ad6_pairs, np_pairs = pairs(self.ad6_matrix), pairs(self.np_matrix)
        under = np_pairs - ad6_pairs   # NetPlumber reachable, ad6 drops it: unsound
        over = ad6_pairs - np_pairs    # ad6 reachable, NetPlumber doesn't: over-approx
        self.assertEqual(
            under, set(),
            "ad6 UNSOUND on the N=2 slice -- dropped a pair NetPlumber reaches: %s" % under)
        self.assertEqual(
            over, set(),
            "ad6 over-approximates on the N=2 slice vs NetPlumber: %s" % over)


if __name__ == '__main__':
    unittest.main()
