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

""" APKeep scale validation on wl_i2 (Internet2) -- APKEEP_BACKEND.md, P5.

wl_i2 is the large workload: 9 routers decomposed into 18 in/out switches with a
~77k-entry destination-IP FIB. Unlike wl_ifi (the DHSA device model) it is an HSA
transfer-function benchmark, but its out-tables are a clean dst-IP FIB and its
in-tables collapse to a single internal port (the VLAN is just link identity, as
in wl_ifi), so the adapter translates it exactly. This pins that: FaVe+APKeep
reachability == the policy oracle reachable.json (missing=0, extra=0).

This is the correctness companion to the from-zero scale comparison in
bench/apkeep_vs_netplumber.py (where APKeep is ~24x faster than NetPlumber here).
The model JSON are gitignored generated artifacts; test/gen_wl_i2_inputs.sh
produces them from tracked inputs before this runs (no live backend). Heavier
than the wl_ifi test (~15 s) -- a deterministic scale gate, not a fast check.
"""

import json
import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter, available

_PREFIX = "bench/wl_i2/i2-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_ORACLE = "bench/wl_i2/reachable.json"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("device_topology.json", "routes.json", "sources.json", "probes.json")] + [_ORACLE]


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@unittest.skipUnless(available(), "JPype or the APKeep jar is unavailable")
@unittest.skipUnless(all(os.path.isfile(f) for f in _INPUTS),
                     "wl_i2 inputs not generated (run test/gen_wl_i2_inputs.sh)")
class TestAPKeepI2(unittest.TestCase):
    """ Real wl_i2 (77k dst-IP routes) -> APKeepAdapter -> reachability == oracle. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_i2")
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

    def test_scale_model_built(self):
        # 9 routers -> 18 in/out switches; a large dst-IP FIB.
        self.assertEqual(len(self.engine._fwd_devices), 18)
        self.assertEqual(len(self.sources), 9)
        self.assertEqual(len(self.probes), 9)
        self.assertGreater(len(self.engine._fwd_rules), 50000)

    def test_reachability_matches_ground_truth(self):
        diffs = {}
        for role in sorted(set(self.reach) | set(self.expected)):
            got = self.reach.get(role, set())
            exp = set(self.expected.get(role, []))
            if got != exp:
                diffs[role] = {"missing": sorted(exp - got), "extra": sorted(got - exp)}
        self.assertEqual(diffs, {}, "i2 reachability differs from reachable.json: %s" % diffs)


if __name__ == '__main__':
    unittest.main()
