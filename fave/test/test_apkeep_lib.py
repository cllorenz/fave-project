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

""" P2 smoke: drive APKeep in-process via JPype (resident JVM) and reproduce the
bundled-Stanford forwarding-loop golden through the in-memory rule-add path.

This is the JPype/LibAPKeep counterpart of the CLI golden pin
(fave/test/apkeep_smoke.sh): same dataset, same 20 loops, but driven via the
embeddable in-process API (run() takes a Python list of rule strings, not a
file) -- proving the binding is equivalent to the batch CLI. Needs JDK 11 + the
built APKeep jar; skips cleanly otherwise.
"""

import unittest

import os

from apkeep.lib_apkeep import LibAPKeep, available

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SNAPSHOT = os.path.join(_REPO_ROOT, "apkeep", "networks", "stanford")
_GOLDEN = os.path.join(_REPO_ROOT, "fave", "test", "apkeep_stanford_loops.golden")


@unittest.skipUnless(available(), "JPype or the APKeep jar is unavailable")
class TestLibAPKeep(unittest.TestCase):
    """ LibAPKeep (in-process) must reproduce the CLI golden loop set. """

    def test_stanford_loops_in_memory(self):
        apk = LibAPKeep()
        apk.init_snapshot(_SNAPSHOT)

        # In-memory rule add: read the update trace into a Python list and feed
        # it directly (no file handed to APKeep to parse).
        with open(os.path.join(_SNAPSHOT, "updates")) as handle:
            rules = [line.strip() for line in handle]
        apk.run(rules)

        loops = set(apk.get_loops())
        with open(_GOLDEN) as handle:
            golden = set(handle.read().splitlines())

        self.assertEqual(len(loops), 20, "expected 20 Stanford loops")
        self.assertEqual(loops, golden, "in-process loop set diverged from the golden")


if __name__ == '__main__':
    unittest.main()
