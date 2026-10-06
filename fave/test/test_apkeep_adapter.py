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
from apkeep.adapter import (APKeepAdapter, available, _lpm_destinations,
                            _restrict_dst)
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

        cls.adapter = APKeepAdapter(_logger(), faithful_vlan=False, engine='bdd')
        for model in (router, switch):
            cls.adapter.add_tables(model)
            cls.adapter.add_rules(model)
        for sport, dport in [("source.A.1", "r.1"), ("r.2", "sw.1"),
                             ("sw.3", "probe.B.1"), ("sw.2", "probe.C.1")]:
            cls.adapter.add_link(sport, dport)
        cls.adapter.add_generator(SimpleNamespace(node='source.A'))
        cls.adapter.add_probe(SimpleNamespace(node='probe.B'))
        cls.adapter.add_probe(SimpleNamespace(node='probe.C'))
        # Taken BEFORE any query: the build releases the translation buffers
        # (`_release_build_buffers`), so they are only readable until then.
        cls.translated = list(cls.adapter._fwd_rules)
        cls.rewritten_before_build = cls.adapter._rewritten_fields()

    def test_translation(self):
        # "+ fwd <dev> <prefix> <len> <port> <priority>"; priority == prefix len
        # so longest-prefix-match wins regardless of rule arrival order.
        self.assertIn("+ fwd r 167772160 8 2 8", self.translated)  # 10.0.0.0/8 -> port 2
        self.assertIn("+ fwd sw 167772160 8 3 8", self.translated)  # 10.0.0.0/8 -> port 3
        self.assertIn("source.A 1 r 1", self.adapter._edges)
        self.assertIn("sw 3 probe.B 1", self.adapter._edges)

    def test_the_build_releases_its_buffers(self):
        """ Once the engine holds the rules, the per-rule buffers go -- as
        None, so a later reader fails instead of seeing an empty table -- and
        the one query-time reader is answered from what they held. """
        self.adapter.clear_results()
        self.adapter.check_compliance({"probe.B": [("source.A", False, None)]})
        self.assertIsNone(self.adapter._fwd_rules)
        self.assertIsNone(self.adapter._fwd_ingress)
        self.assertIsNone(self.adapter._fwd_table)
        self.assertEqual(self.adapter._rewritten_fields(),
                         self.rewritten_before_build)
        self.assertEqual(self.adapter._build_metrics['fwd_rules_translated'],
                         len(self.translated))

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


class TestOutInterfaceResolvedAgainstTheFib(unittest.TestCase):
    """ `-o` is resolved against the FIB, not skipped and not ignored.

    `-o N` means "will leave by interface N". FaVe runs filter chains BEFORE
    routing, so the egress is unknown when the rule is evaluated -- which is why
    the adapter used to drop such rules outright. Both of the simple answers are
    wrong, and the V5 campaign measured both:

    * **skipping** loses an `-o` ACCEPT's permit. `wl_example`'s `pgf` is
      `-P FORWARD DROP` plus one `-o 1 -s <office> -j ACCEPT`, and with the rule
      dropped both APKeep engines reported `source.office does not reach
      probe.internet` where NetPlumber, ad6 and VeriFlow-FR all say it does.
    * **ignoring the qualifier** over-applies an `-o` DROP. `wl_up`'s two
      `-o 1 -d <own /48> -j DROP` rules are anti-spoofing over its ENTIRE
      address space, and emitting them port-agnostically produced 3025 false
      violations of 18,811.

    The egress is a function of the destination and the FIB is already
    materialised, so the rule is equivalent to itself restricted to the
    destinations that route to that port. These pin the arithmetic.
    """

    #: wl_example's `pgf`: two connected /120s and a default route out the
    #: uplink -- the minimal shape that has both a specific and a default route.
    FIB = [("2001:db8::100/120", "2", 120),
           ("2001:db8::200/120", "3", 120),
           (None, "1", 0)]

    def test_a_specific_route_is_its_own_prefix(self):
        self.assertEqual(_lpm_destinations(self.FIB, "2"),
                         ["2001:db8::100/120"])
        self.assertEqual(_lpm_destinations(self.FIB, "3"),
                         ["2001:db8::200/120"])

    def test_the_default_route_excludes_the_more_specific_ones(self):
        """ LPM, not containment: both /120s are INSIDE ::/0, and a packet to
        either leaves by 2 or 3, never by 1. """
        import ipaddress
        pieces = _lpm_destinations(self.FIB, "1")
        self.assertTrue(pieces, "the default route must yield destinations")
        self.assertNotIn(None, pieces, "::/0 whole would include the /120s")
        for internal in ("2001:db8::100/120", "2001:db8::200/120"):
            net = ipaddress.ip_network(internal)
            covered = [p for p in pieces
                       if net.subnet_of(ipaddress.ip_network(p))]
            self.assertEqual(covered, [], "%s routes to its own port, not 1"
                             % internal)
        # and the pieces must still cover something outside them
        outside = ipaddress.ip_network("2001:db8::300/120")
        self.assertTrue(any(outside.subnet_of(ipaddress.ip_network(p))
                            for p in pieces))

    def test_a_same_egress_child_is_kept(self):
        """ A more-specific route to the SAME port still routes there, so it is
        not carved out -- only a DIFFERENT egress is. """
        import ipaddress
        fib = [("10.0.0.0/8", "1", 8), ("10.1.0.0/16", "1", 16)]
        pieces = _lpm_destinations(fib, "1")
        net = ipaddress.ip_network("10.1.0.0/16")
        self.assertTrue(any(net.subnet_of(ipaddress.ip_network(p))
                            for p in pieces))

    def test_the_route_unknown_discard_is_not_an_egress(self):
        """ `__drop__` destinations leave by no port, so they are carved out of
        a covering route just as a different physical egress would be. """
        import ipaddress
        fib = [(None, "1", 0), ("10.9.0.0/16", "__drop__", 16)]
        pieces = _lpm_destinations(fib, "1")
        net = ipaddress.ip_network("10.9.0.0/16")
        self.assertFalse(any(net.subnet_of(ipaddress.ip_network(p))
                             for p in pieces))

    def test_a_device_with_no_fib_resolves_nothing(self):
        """ A terminal filter (wl_tum's fw.tum) has no routing, so there is
        nothing to resolve against and the rule is emitted for no destination.
        Honest, and the pre-existing behaviour for that shape. """
        self.assertEqual(_lpm_destinations([], "1"), [])

    def test_a_rules_own_destination_is_narrowed_not_replaced(self):
        self.assertEqual(_restrict_dst(None, "10.0.0.0/8"), "10.0.0.0/8")
        self.assertEqual(_restrict_dst("10.1.0.0/16", "10.0.0.0/8"),
                         "10.1.0.0/16")          # rule's dst is narrower
        self.assertEqual(_restrict_dst("10.0.0.0/8", "10.1.0.0/16"),
                         "10.1.0.0/16")          # the route's piece is narrower
        self.assertIs(_restrict_dst("192.168.0.0/16", "10.0.0.0/8"), False)
        self.assertIs(_restrict_dst("2001:db8::/32", "10.0.0.0/8"), False)
