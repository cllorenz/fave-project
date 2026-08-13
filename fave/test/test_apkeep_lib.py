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

""" In-process APKeep (libapkeep) tests: the JPype-driven binding (P2) and the
reachability solver (P3).

APKeep allocates a single, large (100M-node) BDD table and keeps its network in
static fields, and JPype's JVM is process-global and resident -- so there can be
only ONE APKeep network per process (a second APKeep.init OOMs allocating a
second BDD table). All checks therefore share ONE network built once in
setUpClass, rather than re-initialising per test.

P2 (test_stanford_loops_in_memory): drive the bundled Stanford dataset through
the in-memory rule-add path and reproduce the CLI golden loop set -- proving the
binding is equivalent to the batch CLI.

P3 (test_reachability_*): functional checks that ReachabilityChecker propagates
and terminates correctly (reaches a real forwarding port; rejects a bogus device
and a zero-AP port). Rigorous reachability correctness is the P5 differential vs
NetPlumber (APKEEP_BACKEND.md).
"""

import unittest

import os

from apkeep.lib_apkeep import LibAPKeep, available
from test.backend_gate import require_or_skip

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SNAPSHOT = os.path.join(_REPO_ROOT, "apkeep", "networks", "stanford")
_GOLDEN = os.path.join(_REPO_ROOT, "fave", "test", "apkeep_stanford_loops.golden")


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestLibAPKeep(unittest.TestCase):
    """ All checks share one in-process APKeep network (one per process). """

    @classmethod
    def setUpClass(cls):
        cls.apk = LibAPKeep()
        cls.apk.init_snapshot(_SNAPSHOT)
        # in-memory rule add: feed the update trace as a Python list, not a file
        with open(os.path.join(_SNAPSHOT, "updates")) as handle:
            cls.apk.run([line.strip() for line in handle])

    # --- P2: in-process binding reproduces the CLI golden ---

    def test_stanford_loops_in_memory(self):
        loops = set(self.apk.get_loops())
        with open(_GOLDEN) as handle:
            golden = set(handle.read().splitlines())
        self.assertEqual(len(loops), 20, "expected 20 Stanford loops")
        self.assertEqual(loops, golden, "in-process loop set diverged from the golden")

    # --- P3: reachability solver (functional) ---

    def test_reachability_reaches_forwarding_port(self):
        # bbra_rtr.te7/1 links to bbrb_rtr.te7/1; in the final state bbrb_rtr
        # routes (almost) everything via `default`, so that port carries APs and
        # must be reachable.
        self.assertTrue(self.apk.is_reachable("bbra_rtr", "te7/1", "bbrb_rtr", "default"))

    def test_reachability_bogus_target_unreachable(self):
        self.assertFalse(self.apk.is_reachable("bbra_rtr", "te7/1", "no_such_device", "p0"))

    def test_reachability_zero_ap_port_unreachable(self):
        # bbrb_rtr.te6/1 forwards no APs in the final state -> not reachable.
        self.assertFalse(self.apk.is_reachable("bbra_rtr", "te7/1", "bbrb_rtr", "te6/1"))


if __name__ == '__main__':
    unittest.main()
