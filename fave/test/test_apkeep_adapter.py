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

""" P4 test for APKeepAdapter: FaVe device models -> APKeep, compliance via
reachability.

Drives the adapter with a hand-built forwarding-only model (a router and a
switch, both dst-IP forwarders, plus a source and two probes) and checks that:
the FaVe rules translate to the expected APKeep `+ fwd` lines and topology
edges; a satisfied reach-rule yields no violation; a violated "must not reach"
and an unreachable "must reach" each yield a violation. Forwarding-only (no
ACLs/VLANs); the full wl_ifi run + the NetPlumber differential are P5.
"""

import unittest

from types import SimpleNamespace

from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

_DST = 'packet.ipv4.destination'


def _logger():
    import logging
    log = logging.getLogger("test_apkeep_adapter")
    log.setLevel(logging.WARNING)
    return log


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestAPKeepAdapter(unittest.TestCase):
    """ A router r (dst 10/8 -> port 2) and switch sw (dst 10/8 -> port 3),
    wired source.A -> r -> sw -> probe.B; probe.C hangs off an unused switch
    port (unreachable). """

    @classmethod
    def setUpClass(cls):
        # router: routing rule rewrites out_port=r.2_egress (-> APKeep port 2)
        router = SimpleNamespace(node='r', tables={'r.routing': [
            Rule('r', 'r.routing', 0, ['r.routing_in'],
                 Match([RuleField(_DST, '10.0.0.0/8')]),
                 [Rewrite([RuleField('out_port', 'r.2_egress')]),
                  Forward(['r.routing_out'])])
        ]})
        # switch: forwards dst 10/8 to sw.3
        switch = SimpleNamespace(node='sw', tables={'sw.1': [
            Rule('sw', 'sw.1', 0, ['sw.1', 'sw.2'],
                 Match([RuleField(_DST, '10.0.0.0/8')]), [Forward(['sw.3'])])
        ]})

        cls.adapter = APKeepAdapter(_logger())
        for model in (router, switch):
            cls.adapter.add_tables(model)
            cls.adapter.add_rules(model)
        for sport, dport in [("source.A.1", "r.1"), ("r.2", "sw.1"),
                             ("sw.3", "probe.B.1"), ("sw.2", "probe.C.1")]:
            cls.adapter.add_link(sport, dport)
        cls.adapter.add_generator(SimpleNamespace(node='source.A'))
        cls.adapter.add_probe(SimpleNamespace(node='probe.B'))
        cls.adapter.add_probe(SimpleNamespace(node='probe.C'))

    def test_translation(self):
        # "+ fwd <dev> <prefix> <len> <port> <priority>"; priority == prefix len
        # so longest-prefix-match wins regardless of rule arrival order.
        self.assertIn("+ fwd r 167772160 8 2 8", self.adapter._fwd_rules)  # 10.0.0.0/8 -> port 2
        self.assertIn("+ fwd sw 167772160 8 3 8", self.adapter._fwd_rules)  # 10.0.0.0/8 -> port 3
        self.assertIn("source.A 1 r 1", self.adapter._edges)
        self.assertIn("sw 3 probe.B 1", self.adapter._edges)

    def test_compliant_reach_no_violation(self):
        self.adapter.clear_results()
        self.adapter.check_compliance({"probe.B": [("source.A", False, None)]})
        self.assertEqual(self.adapter.get_compliance_results(), [])

    def test_violated_must_not_reach(self):
        self.adapter.clear_results()
        self.adapter.check_compliance({"probe.B": [("source.A", True, None)]})
        self.assertEqual(self.adapter.get_compliance_results(),
                         [("source.A", "probe.B", False, "")])

    def test_unreachable_expected_reach(self):
        self.adapter.clear_results()
        self.adapter.check_compliance({"probe.C": [("source.A", False, None)]})
        self.assertEqual(self.adapter.get_compliance_results(),
                         [("source.A", "probe.C", True, "")])


if __name__ == '__main__':
    unittest.main()
