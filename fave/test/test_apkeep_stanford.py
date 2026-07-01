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

""" APKeep on wl_stanford (Stanford backbone HSA) -- APKEEP_BACKEND.md, P7.

wl_stanford decomposes each of 16 routers into in./mid./out. switches. mid. is a
dst-IP FIB; in. is the ingress ACL (a pass-through for forwarding); out. is an
input-port->output-port permutation (a pure wire) that a dst-IP ForwardElement
cannot express. The adapter collapses the out. stage into the topology, wiring
each mid. egress interface straight to its external neighbour (see
APKeepAdapter._collapse_out_stage), so 48 switches become 32 ForwardElements.

This pins forwarding correctness: FaVe+APKeep reachability == the shipped policy
oracle reachable.json (missing=0, extra=0). NOTE that reachable.json is the
all-to-all existential reachability from the original HSA/NetPlumber papers -- it
is fully connected (240/240 router pairs), so it validates forwarding
completeness but has NO deny cases and therefore does not exercise the ingress/
egress ACLs the forwarding model ignores. The ACL-sensitive, forbidden-
reachability cross-check against NetPlumber lives in test_apkeep_stanford_deny.py.

The model JSON are gitignored generated artifacts; test/gen_wl_stanford_inputs.sh
produces them from tracked inputs before this runs (no live backend).
"""

import json
import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter, available

_PREFIX = "bench/wl_stanford/stanford-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_ORACLE = "bench/wl_stanford/reachable.json"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("device_topology.json", "routes.json", "sources.json", "probes.json")] + [_ORACLE]


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@unittest.skipUnless(available(), "JPype or the APKeep jar is unavailable")
@unittest.skipUnless(all(os.path.isfile(f) for f in _INPUTS),
                     "wl_stanford inputs not generated (run test/gen_wl_stanford_inputs.sh)")
class TestAPKeepStanford(unittest.TestCase):
    """ Real wl_stanford -> APKeepAdapter (out-stage collapsed) -> reach == oracle. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_stanford")
        log.setLevel(logging.WARNING)
        cls.engine = APKeepAdapter(log)

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX, files=_FILES)
            cls.sources = sorted(cls.engine._generators)
            cls.probes = sorted(cls.engine._probes)
            rules = {p: [[s, False, []] for s in cls.sources] for p in cls.probes}
            fave.check_compliance(rules)

        not_reachable = {
            (s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()
        }
        cls.reach = {
            _base(p): set(
                _base(s) for s in cls.sources
                if (s, p) not in not_reachable and _base(s) != _base(p)
            )
            for p in cls.probes
        }
        with open(_ORACLE) as raw:
            cls.expected = json.load(raw)

    def test_out_stage_collapsed(self):
        # 16 routers x {in, mid, out}; the out. stage is collapsed into the
        # topology, so only the 16 in. + 16 mid. switches remain as devices.
        self.assertTrue(self.engine._stanford)
        self.assertEqual(len(self.engine._fwd_devices), 32)
        self.assertEqual(len(self.sources), 16)
        self.assertEqual(len(self.probes), 16)

    def test_reachability_matches_ground_truth(self):
        diffs = {}
        for role in sorted(set(self.reach) | set(self.expected)):
            got = self.reach.get(role, set())
            exp = set(self.expected.get(role, []))
            if got != exp:
                diffs[role] = {"missing": sorted(exp - got), "extra": sorted(got - exp)}
        self.assertEqual(diffs, {}, "stanford reachability differs from reachable.json: %s" % diffs)


if __name__ == '__main__':
    unittest.main()
