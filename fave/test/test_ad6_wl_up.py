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

""" wl_up through Ad6Adapter (AD6_PLAN.md §5.1) -- a structurally DIFFERENT
FaVe device model from wl_ifi's Cisco-ACL router: wl_up's 136 devices are
`packet_filter`/`host` models, each with its own real `ip6tables` ruleset
(bench/wl_up/rulesets/*-ruleset, confirmed byte-identical to ad6's own
bundled bench/up rulesets). Rule CONTENT for these devices is sourced from
ad6's native IP6TablesParser directly (Ad6Adapter.load_bench_metadata),
not hand-translated field by field; only topology wiring, dst-LPM routing,
and the to-self/in-transit dispatch (ad6/src/parser/favemodel.py's
_build_ruleset_firewall/_routing_table/_dispatch_table) are new adapter-side
work. See that module's docstrings for the full mechanism.

This is deliberately NOT a full differential against reachable.json (unlike
test_ad6_wl_ifi.py) -- see the class docstring below for why wl_up's real
rulesets make strict equality against reachable.json the wrong bar, and
AD6_PLAN.md §5.1 for the open methodology question this surfaces. It is:
  (a) a structural smoke test (network builds, right device/generator/probe
      counts), and
  (b) a small, hand-picked characterization of the stateful query-forcing
      mechanism (built for wl_ifi's `<->>` checks, AD6_PLAN.md §4.2) against
      a handful of REAL wl_up compliance pairs -- proving it produces
      DIFFERENTIATED (not vacuously-all-true) results here too, once the
      query is both src-seeded AND state-forced.
The full bench/wl_up/cchecks.json (11902 entries, ~0.5s/query observed) is
a ~1-2 hour run -- a bench script, not a routine test; see AD6_PLAN.md §5.1.
"""

import logging
import os
import unittest

from ad6.adapter import Ad6Adapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_up"

_INPUTS = [
    "%s/%s" % (_PREFIX, f) for f in
    ("topology.json", "routes.json", "sources.json", "policies.json", "reachable.json")
]


def _inputs_present():
    return all(os.path.isfile(f) for f in _INPUTS) and os.path.isdir("%s/rulesets" % _PREFIX)


def _related(value):
    return [{"name": "related", "value": value, "negated": False}]


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_up inputs/rulesets not present (bench/wl_up/rulesets is gitignored)")
class TestAd6WlUp(unittest.TestCase):
    """ wl_up's packet_filter/host device model, structurally, plus the
    stateful query-forcing mechanism on a handful of real pairs.

    Why not a reachable.json differential like test_ad6_wl_ifi.py: wl_up's
    real ip6tables rulesets carry operationally-necessary rules reach.txt's
    policy matrix never modelled as role-to-role reachability at all -- e.g.
    dmz-file's `-s 2001:db8:abc::0/48 -d ... --dport 22 -j ACCEPT` grants SSH
    to file.uni-potsdam.de from EVERY internal /48 subnet (a blanket admin
    rule), including clients.hssport.uni-potsdam.de, which is NOT in
    reachable.json's 29-role list for that target. Traced and confirmed
    real (not a translation bug): clients.hssport's own seeded src CIDR
    (2001:db8:abc:d::100/120) genuinely falls inside that /48, so an
    existential, state=NEW-forced, src-seeded query correctly finds it
    SSH-reachable. reachable.json reflects reach.txt's policy-matrix marks,
    not a claim that every OTHER pair is unreachable -- so strict equality
    against it is the wrong bar here (unlike wl_ifi, whose ACLs were
    generated to match the policy 1:1). cchecks.json's explicit
    (source, probe, negated, cond) tuples are the right comparison target
    instead, mirroring wl_ifi's own characterization-test approach
    (test_ad6_wl_ifi_stateful.py) -- deferred to a bench script given the
    ~1-2 hour full run time (AD6_PLAN.md §5.1).

    Also confirmed while building this: an UNCONSTRAINED (no state forcing)
    query against wl_up is close to vacuously "always reachable" -- every
    chain here has an unconditional `-m conntrack --ctstate ESTABLISHED -j
    ACCEPT`, and static header-space analysis (ad6, or any HSA-style tool)
    cannot distinguish a genuinely-established connection's packet from one
    that merely claims to be, since "established" is session state the
    firewall tracks, not a real per-packet header bit -- forcing state=NEW
    (this class's _related('0') pairs) is what recovers a meaningful,
    differentiated answer. This is exactly the gap FaVe's `<->>` 3-check
    semantics (AD6_PLAN.md §1.2) exists to paper over via static analysis;
    it is not an ad6-specific limitation. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_up")
        log.setLevel(logging.WARNING)
        cls.engine = Ad6Adapter(log)
        cls.engine.load_bench_metadata(_PREFIX)

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            cls.sources = sorted(cls.engine._generators)
            cls.probes = sorted(cls.engine._probes)

            # Must-NOT-reach checks, state forced to NEW: a handful of real
            # pairs whose expected answer we independently traced (module
            # docstring) rather than trusting reachable.json wholesale.
            rules = {
                "probe.file.uni-potsdam.de": [
                    # file.api.uni-potsdam.de: no SSH grant, no shared /48
                    # admin rule applies to it specifically as a SOURCE --
                    # traced: correctly blocked.
                    ["source.file.api.uni-potsdam.de", True, _related("0")],
                    # adm.uni-potsdam.de: reachable.json says yes; also has
                    # its own explicit permit in dmz-file's ruleset.
                    ["source.adm.uni-potsdam.de", False, _related("0")],
                ],
            }
            fave.check_compliance(rules)

        cls.violations = cls.engine.get_compliance_results()

    def test_network_built(self):
        # 159 devices (136 ruleset-bearing packet_filter/host + 23 switches
        # + pgf counted once among the 136); 137 generators/probes (n=137,
        # AD6_PLAN.md §1.3's flagship count).
        self.assertEqual(len(self.engine._devices), 159)
        self.assertEqual(len(self.sources), 137)
        self.assertEqual(len(self.probes), 137)
        self.assertGreater(len(self.engine._routing_rules), 100)

    def test_ruleset_devices_loaded(self):
        self.assertEqual(len(self.engine._ruleset_text), 136)
        self.assertIn("pgf.uni-potsdam.de", self.engine._ruleset_text)

    def test_stateful_checks_on_real_pairs(self):
        self.assertEqual(
            self.violations, [],
            "ad6 disagrees with the independently-traced expectation for "
            "these pairs: %s" % self.violations)


if __name__ == '__main__':
    unittest.main()
