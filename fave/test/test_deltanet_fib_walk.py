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

""" The reference walk agrees with airtel's matrix, on both traces
(CLOUD_BENCH_PLAN.md §2.15).

`wl_berkeley`'s policy is stated FROM `fib_walk`, so the walk has to be
validated somewhere its answer is known independently. Airtel's matrix is: it
is derived from the homing alone (`policy.py`), and every engine agrees with it
(§2.13). So the walk over airtel's MODEL must reproduce `reachable.json` cell
for cell -- 210 pairs on each trace, no diagonal, no loop.

The second assertion pins what §3 recorded about airtel: its matrix is BLIND to
LPM, so inverting the priority must change nothing. If it ever does, either the
model changed or the walk did, and §2.15's claim that Berkeley's matrix -- which
does change -- sees LPM where airtel's cannot would need re-examining.

Integration tier: `reachable.json` is generated (`gen_deltanet_inputs.sh`), and
the two walks take ~10 s.
"""

import json
import os
import unittest

from bench.deltanet.fib_walk import LOOP, reachability, reached_pairs
from bench.deltanet.preparation import build_model
from bench.deltanet.registry import WORKLOADS, prefix_of
from test.backend_gate import require_or_skip
from test.test_deltanet_model import _load


@require_or_skip(
    all(os.path.isfile(os.path.join(prefix_of(n), 'reachable.json'))
        for n in WORKLOADS),
    "Delta-net workload inputs not generated (run test/gen_deltanet_inputs.sh)")
class TestWalkAgreesWithAirtel(unittest.TestCase):

    def _check(self, which, name):
        inserts, topology, homed = _load(which)
        model = build_model(inserts, topology, homed)
        walked = reachability(model)
        with open(os.path.join(prefix_of(name), 'reachable.json')) as handle:
            oracle = json.load(handle)
        expected = {(s, p) for p, sources in oracle.items() for s in sources}

        self.assertEqual(len(expected), 210)
        self.assertEqual(reached_pairs(walked), expected,
                         "the walk and %s's homing-derived matrix disagree"
                         % name)
        self.assertFalse([k for k in walked if k[1] == LOOP])
        self.assertEqual(
            reached_pairs(reachability(model, resolve='shortest')), expected,
            "inverting LPM changed %s's matrix, which §3 recorded as blind to "
            "it" % name)

    def test_airtel1(self):
        self._check(0, 'wl_airtel1')

    def test_airtel2(self):
        self._check(1, 'wl_airtel2')


if __name__ == '__main__':
    unittest.main()
