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

""" Full wl_ifi end-to-end for APKeepAdapter (APKEEP_BACKEND.md, P4).

Unlike test_apkeep_adapter (a hand-built two-device model), this drives the
*real* wl_ifi device models -- the router `ifi`, its 16 switches, 17 generators
and 17 probes, including the router's acl_in/acl_out -- through the *real*
aggregator dispatch (InProcessFaVe wraps an in-process AggregatorService whose
engine is the APKeepAdapter), then computes the full source->probe reachability
matrix and checks it against the benchmark's ground-truth reachable.json (which
is produced by the NetPlumber-backed pipeline).

With ACL translation the match is EXACT: the router ACLs are wired as per-port
APKeep ACLElements (the VLAN becomes structural -- which port's element), and a
query is seeded with the source's src-IP so source-matching ACLs bite. The only
reachability the policy matrix never asks about is intra-switch self-reach
(source.X -> probe.X), which never traverses the router and so cannot be ACL-
filtered; it is excluded from the comparison, exactly as reachable.json omits it.
"""

import json
import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_ifi"

# The wl_ifi model JSON are gitignored generated artifacts; the integration tier
# produces them via test/gen_wl_ifi_inputs.sh before this test runs. Skip cleanly
# (rather than erroring) when invoked without that generation step.
_INPUTS = [
    "%s/%s" % (_PREFIX, f) for f in
    ("topology.json", "routes.json", "sources.json", "policies.json", "reachable.json")
]


def _inputs_present():
    return all(os.path.isfile(f) for f in _INPUTS)


def _base(name):
    """ "source.external.ifi"/"probe.admin.ifi" -> "external.ifi"/"admin.ifi";
    "source.Internet" -> "Internet". """
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
class TestAPKeepWlIfi(unittest.TestCase):
    """ Real wl_ifi (forwarding + ACLs) -> APKeepAdapter -> reachability, which
    must match reachable.json exactly. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_wl_ifi")
        log.setLevel(logging.WARNING)
        cls.engine = APKeepAdapter(log)

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            cls.sources = sorted(cls.engine._generators)  # "source.X"
            cls.probes = sorted(cls.engine._probes)        # "probe.Y"
            # "must reach" for every (source, probe): a recorded violation means
            # the pair is NOT reachable.
            rules = {p: [[s, False, []] for s in cls.sources] for p in cls.probes}
            fave.check_compliance(rules)

        not_reachable = {
            (s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()
        }
        # base-name reachability matrix, excluding intra-switch self-reach (the
        # policy matrix never asks source.X -> probe.X; it never hits the router).
        cls.reach = {
            _base(p): set(
                _base(s) for s in cls.sources
                if (s, p) not in not_reachable and _base(s) != _base(p)
            )
            for p in cls.probes
        }
        with open("%s/reachable.json" % _PREFIX) as raw:
            cls.expected = json.load(raw)

    def test_network_built(self):
        # 1 router + 16 switches; 17 generators; 17 probes.
        self.assertEqual(len(self.engine._fwd_devices), 17)
        self.assertEqual(len(self.sources), 17)
        self.assertEqual(len(self.probes), 17)
        self.assertGreater(len(self.engine._fwd_rules), 17)

    def test_acls_translated(self):
        # the router's ACLs were captured and translated.
        self.assertEqual(self.engine._acl_device, 'ifi')
        self.assertTrue(self.engine._acl_in)
        self.assertTrue(self.engine._acl_out)

    def test_reachability_matches_ground_truth(self):
        """ Exact match to reachable.json (self-reach excluded). """
        diffs = {}
        for role in sorted(set(self.reach) | set(self.expected)):
            got = self.reach.get(role, set())
            exp = set(self.expected.get(role, []))
            if got != exp:
                diffs[role] = {
                    "missing": sorted(exp - got),  # reachable.json says reachable, APKeep doesn't
                    "extra": sorted(got - exp),    # APKeep reachable, reachable.json doesn't
                }
        self.assertEqual(diffs, {}, "reachability differs from reachable.json: %s" % diffs)


if __name__ == '__main__':
    unittest.main()
