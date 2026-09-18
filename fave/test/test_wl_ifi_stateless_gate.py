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

""" wl_ifi's stateless policy variant, end to end: ZERO violations.

The stateful configuration's oracle is 27 violations -- genuine ones, since the
policy asks for stateful reachability and the model's Cisco ACLs cannot express
it (NetPlumber and APKeep both report exactly those 27, set-identical). A
nonzero expected set makes a poor gate: it has to be spelled out, and it is
satisfied by a tool that drops the condition just as well as by one that
honours it.

The `<-->` variant asks only what the model can answer, so the expectation is
simply **none**. That is the check this file is: a tool that can process a
stateless policy at all reports no violations, and any regression shows up as a
count rather than as a diff against a hand-maintained set.

Driven through the same InProcessFaVe path as the other wl_ifi backend tests.
APKeep only, deliberately: a resident JVM in the same process makes NetPlumber
misreport (see test_apkeep_tum.py), and the NetPlumber side of this comparison
belongs to the benchmark driver, which runs it in its own process.
"""

import json
import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_ifi"
_CCHECKS = "%s/cchecks_stateless.json" % _PREFIX
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("topology.json", "routes.json", "sources.json", "policies.json")]


def _inputs_present():
    return os.path.isfile(_CCHECKS) and all(os.path.isfile(f) for f in _INPUTS)


def _load_rules():
    """ cchecks.json is keyed by SOURCE and stores `valid` (True = must reach),
    which is the OPPOSITE polarity to check_compliance's `negated` -- see the
    long note in test_ad6_wl_ifi_stateful.py, which this mirrors. Inverting
    both the key and the bit gives the probe-keyed (source, negated, cond)
    shape every backend expects. """
    with open(_CCHECKS) as raw:
        by_source = json.load(raw)
    rules = {}
    for source, entries in by_source.items():
        for probe, valid, cond in entries:
            rules.setdefault(probe, []).append([source, not valid, list(cond)])
    return rules


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_ifi stateless inputs not generated "
                 "(run test/gen_wl_ifi_inputs.sh)")
class TestWlIfiStatelessGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        cls.rules = _load_rules()
        log = logging.getLogger("test_wl_ifi_stateless_gate")
        log.setLevel(logging.CRITICAL)
        engine = APKeepAdapter(log, faithful_vlan=False, engine='bdd')
        with InProcessFaVe(engine) as fave:
            fave.replay(_PREFIX)
            fave.check_compliance(cls.rules)
            cls.violations = engine.get_compliance_results()

    def test_the_variant_asks_nothing_about_state(self):
        """ If a condition ever reappears here the gate below stops meaning
        what it says, so this is checked rather than assumed. """
        conds = [cond for entries in self.rules.values()
                 for _, _, cond in entries if cond]
        self.assertEqual(conds, [])

    def test_it_is_the_full_check_set(self):
        """ 272 = the stateful set's 299 with each of the 27 stateful PAIRS
        collapsed to one plain check. """
        self.assertEqual(sum(len(v) for v in self.rules.values()), 272)

    def test_zero_violations(self):
        self.assertEqual(
            [], self.violations,
            "a stateless policy over wl_ifi must be satisfiable in full")


if __name__ == '__main__':
    unittest.main()
