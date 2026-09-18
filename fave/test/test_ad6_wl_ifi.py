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

""" Full wl_ifi end-to-end for Ad6Adapter (AD6_PLAN.md §4.2/§4.3/§4.4).

Mirrors test_apkeep_wl_ifi.py: drives the real wl_ifi device models -- the
router `ifi`, its 16 switches, 17 generators, 17 probes, including the
router's acl_in/acl_out -- through the real aggregator dispatch
(InProcessFaVe wraps an in-process AggregatorService whose engine is the
Ad6Adapter), then computes the full source->probe reachability matrix and
checks it against reachable.json.

Ad6Adapter buffers the same neutral model APKeepAdapter/NetPlumberLibAdapter
see, but never runs ad6 in-process (see fave/ad6/adapter.py's module
docstring) -- check_compliance() serialises it to JSON and drives
ad6/fave_bridge.py as a subprocess, which builds the ad6 Kripke/SAT model via
ad6/src/parser/favemodel.py (the FaVe-model-to-ad6 translator, AD6_PLAN.md
§4.4) and answers every pair in one process.
"""

import json
import logging
import os
import unittest

from ad6.adapter import Ad6Adapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_ifi"

# The wl_ifi model JSON are gitignored generated artifacts; the integration
# tier produces them via test/gen_wl_ifi_inputs.sh before this test runs.
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


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
class TestAd6WlIfi(unittest.TestCase):
    """ Real wl_ifi (forwarding + ACLs) -> Ad6Adapter -> reachability, which
    must match reachable.json exactly. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_ifi")
        log.setLevel(logging.WARNING)
        cls.engine = Ad6Adapter(log)

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            cls.sources = sorted(cls.engine._generators)  # "source.X"
            cls.probes = sorted(cls.engine._probes)        # "probe.Y"
            # "must reach" for every (source, probe): a recorded violation
            # means the pair is NOT reachable.
            rules = {p: [[s, False, []] for s in cls.sources] for p in cls.probes}
            fave.check_compliance(rules)

        not_reachable = {
            (s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()
        }
        # base-name reachability matrix, excluding intra-switch self-reach
        # (the policy matrix never asks source.X -> probe.X).
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
        """ 1 router + 16 switches; 17 generators; 17 probes. Guards the
        reachability test below: an empty model also "matches" nothing.

        Reads the STRUCTURAL capture (§9.25). This used to count the semantic
        IR's `_devices`/`_fwd_rules`; those were concepts the adapter
        reconstructed, and the corresponding fact now is simply that every
        device arrived with its tables. """
        self.assertEqual(len(self.engine._tables), 17)
        self.assertEqual(len(self.sources), 17)
        self.assertEqual(len(self.probes), 17)
        rules = [rule for tables in self.engine._tables.values()
                 for table_rules in tables.values() for rule in table_rules]
        self.assertGreater(len(rules), 17)

    def test_acls_translated(self):
        """ wl_ifi's one ACL-carrying device is the router. The semantic path
        recorded that as an interpreted `_acl_devices` set; structurally it is
        just which device has `acl_in`/`acl_out` TABLES -- the same fact, read
        off the model instead of inferred from it. """
        acl_devices = {
            device for device, tables in self.engine._tables.items()
            if any(name.endswith(('.acl_in', '.acl_out')) for name in tables)
        }
        self.assertEqual(acl_devices, {'ifi'})
        self.assertTrue(self.engine._tables['ifi'].get('ifi.acl_in'))
        self.assertTrue(self.engine._tables['ifi'].get('ifi.acl_out'))

    def test_reachability_matches_ground_truth(self):
        """ Exact match to reachable.json (self-reach excluded). """
        diffs = {}
        for role in sorted(set(self.reach) | set(self.expected)):
            got = self.reach.get(role, set())
            exp = set(self.expected.get(role, []))
            if got != exp:
                diffs[role] = {
                    "missing": sorted(exp - got),  # reachable.json says reachable, ad6 doesn't
                    "extra": sorted(got - exp),    # ad6 reachable, reachable.json doesn't
                }
        self.assertEqual(diffs, {}, "reachability differs from reachable.json: %s" % diffs)


if __name__ == '__main__':
    unittest.main()
