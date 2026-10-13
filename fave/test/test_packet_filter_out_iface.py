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

""" `-o` in a packet filter's filter chains means what netfilter means: the
rule applies iff ROUTING sends the packet out that interface (owner,
2026-10-10). FaVe's packet filter runs its chains before `routing`, so an `-o X`
rule accepts the slice of a flow tagged `out_port = X`, and `routing` must
forward a tagged packet only by the route its destination actually takes.

Found by the incremental calibration (bench/campaigns/results_inc_dev_20261010
/FINDINGS.md): on `wl_example` with pgf's anti-spoofing rule deleted, or with
one route deleted, NetPlumber and VeriFlow-FR let a `pgf.1`-tagged slice
through to `office`, while APKeep -- which resolves `-o` against the FIB --
did not. The routing table's consistency rules were wrong in two ways: the
default route (index 65535) overflowed its index block and its "exact" rule
ran after the specific routes, which re-tagged the packet; and a shorter
route's exact rule caught packets a longer route owns.
"""

import logging
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import available as apkeep_available
from devices.packet_filter import PacketFilterModel
from netplumber import lib_adapter
from rule.rule_model import Forward, Match, Rule, RuleField
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present
from util import incremental as inc
from veriflow.adapter import VeriFlowAdapter, available as veriflow_available

_PREFIX = 'bench/wl_example'


def _log():
    log = logging.getLogger("test_packet_filter_out_iface")
    log.setLevel(logging.ERROR)
    return log


def _engines():
    return (('netplumber', lambda: lib_adapter.NetPlumberLibAdapter(_log())),
            ('veriflow', lambda: VeriFlowAdapter(_log())),
            ('apkeep', lambda: APKeepAdapter(_log(), engine='bdd')))


def _routing_keys(dst):
    """ The pgf.routing rules derived from the route to `dst`, whatever the
    index layout. """
    from util.in_process_driver import InProcessFaVe
    engine = lib_adapter.NetPlumberLibAdapter(_log())
    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        return {key for key, rule in inc.model_rules(fave)
                if key[1] == 'pgf.routing'
                and any(f.name == 'packet.ipv6.destination' and str(f.value) == dst
                        for f in rule.match)}


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
@require_or_skip(veriflow_available(), "libveriflow_fr is not built")
@require_or_skip(apkeep_available(), "JPype or the APKeep jar is unavailable")
class TestEnginesAgreeOnOutIface(unittest.TestCase):
    """ Built from zero, every engine gives the same verdicts on models where
    only routing decides whether an `-o` rule applies. """

    def _agree(self, deleted, apkeep_may_refuse=False):
        if not inputs_present(_PREFIX):
            require_or_skip(False, "%s inputs not generated" % _PREFIX)(lambda: None)()
            self.skipTest("%s inputs not generated" % _PREFIX)
        checks = inc.load_checks(_PREFIX + '/checks.json')
        got = {}
        for name, make in _engines():
            try:
                got[name] = inc.from_zero(make, _PREFIX, checks, deleted, set())
            except Exception as err:          # BarrierError around the refusal
                if not (name == 'apkeep' and apkeep_may_refuse
                        and 'UntranslatedSemantics' in str(err)):
                    raise
        for name in [n for n in ('veriflow', 'apkeep') if n in got]:
            self.assertEqual(
                {k for k in got['netplumber'] if got['netplumber'][k] != got[name][k]},
                set(), "netplumber and %s disagree" % name)

    def test_the_shipped_model(self):
        self._agree(set())

    def test_without_the_anti_spoofing_rule(self):
        # Internet traffic spoofing office's sources now reaches the forward
        # chain; `-o pgf.1 -s office ACCEPT` must not let it reach office,
        # whose packets routing sends out pgf.3.
        self._agree({('pgf', 'pgf.forward_filter', 0)})

    def test_without_the_dmz_route(self):
        keys = _routing_keys('2001:db8::100/120')
        self.assertTrue(keys)
        self._agree(keys)

    def test_without_any_one_rule_of_a_route(self):
        # An update stream deletes the routing table's rules one at a time,
        # so every partial state of a route is a model the engines must agree
        # on (the calibration's S1 deleted one of them). A route's forwarding
        # rule without its drop is one APKeep's FIB cannot express: it must
        # REFUSE it, never answer differently.
        for dst in ('2001:db8::100/120', '2001:db8::200/120'):
            for key in sorted(_routing_keys(dst)):
                with self.subTest(key=key):
                    self._agree({key}, apkeep_may_refuse=True)


class TestRoutingConsistencyRules(unittest.TestCase):
    """ The routing table a packet filter builds from its routes: a tagged
    packet goes out by the route its destination takes, or nowhere. """

    def _model(self):
        model = PacketFilterModel('pf', ports=['1', '2', '3'])
        model.add_rules([
            Rule('pf', 'pf.routing', 0,
                 match=Match([RuleField('packet.ipv6.destination', '2001:db8::100/120')]),
                 actions=[Forward(ports=['pf.2'])]),
            Rule('pf', 'pf.routing', 1,
                 match=Match([RuleField('packet.ipv6.destination', '2001:db8::/32')]),
                 actions=[Forward(ports=['pf.3'])]),
            Rule('pf', 'pf.routing', 65535, match=Match(),
                 actions=[Forward(ports=['pf.1'])]),
        ])
        return sorted(model._adds['pf.routing'], key=lambda r: r.idx)

    @staticmethod
    def _decide(rows, dst_route, tag):
        """ First-match over the table for a packet whose destination lies in
        exactly the routes `dst_route` names (a set of route destinations,
        None meaning the default) and whose out_port is `tag` (None:
        untagged, i.e. any value). Returns the egress, or None for a drop. """
        for row in rows:
            dst = next((str(f.value) for f in row.match
                        if f.name == 'packet.ipv6.destination'), None)
            if dst is not None and dst not in dst_route:
                continue
            port = next((str(f.value) for f in row.match if f.name == 'out_port'), None)
            if port is not None and tag is not None and port != tag:
                continue
            if port is not None and tag is None:
                return port            # the slice with that tag is the one kept
            if not row.actions:
                return None
            return port or 'rewritten'
        return None

    def test_a_tag_must_be_the_routed_port(self):
        rows = self._model()
        in_both = {'2001:db8::100/120', '2001:db8::/32'}
        self.assertEqual(self._decide(rows, in_both, 'pf.2_egress'), 'pf.2_egress')
        self.assertIsNone(self._decide(rows, in_both, 'pf.3_egress'),
                          "the /32's port, but the /120 routes this packet")
        self.assertIsNone(self._decide(rows, in_both, 'pf.1_egress'),
                          "the default's port, but a specific route applies")
        self.assertEqual(self._decide(rows, set(), 'pf.1_egress'), 'pf.1_egress')
        self.assertIsNone(self._decide(rows, set(), 'pf.3_egress'))

    def test_rules_follow_the_route_order(self):
        rows = self._model()
        order = [next((str(f.value) for f in r.match
                       if f.name == 'packet.ipv6.destination'), 'default') for r in rows]
        self.assertEqual(order, sorted(order, key=['2001:db8::100/120',
                                                   '2001:db8::/32', 'default'].index))


if __name__ == '__main__':
    unittest.main()
