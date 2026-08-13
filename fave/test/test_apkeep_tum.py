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

""" APKeep-vs-NetPlumber on wl_tum -- APKEEP_TUM_UP_PLAN.md, Phase 1.

wl_tum is a single stateful IPv4 firewall (fw.tum, ~3.8k rules) and ships an
*empty* oracle, so NetPlumber is the reference. This test is the CI face of the
bench/apkeep_tum_diff.py differential.

CONVERGENCE GATE (Phase 2/4). The APKeepAdapter models fw.tum's forward_filter
via a FilterElement (multi-field first-match forward-to-out_port / drop), so
FaVe+APKeep and FaVe+NetPlumber must compute the SAME wl_tum reachability
(source.tum -> probe.tum: an injected tcp/80 packet traverses fw.tum's forward
filter to the accept point). This began as a characterize->fix->flip ratchet
pinning the Phase-1 under-approximation; the Phase-2 FilterElement converged it,
so it now asserts exact agreement (like test_apkeep_stanford gates wl_stanford).

NP must run in its OWN process (a resident JVM in-process makes NetPlumber
misreport), so its matrix comes from the differential harness's netplumber
worker subprocess; APKeep runs in-process here.
"""

import os
import sys
import tempfile
import unittest

from apkeep.adapter import APKeepAdapter, available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bench"))

_PREFIX = "bench/wl_tum"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("topology.json", "routes.json", "policies.json", "sources.json",
            "rulesets/tum-ruleset")]


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_tum inputs missing (topology/sources/policies/ruleset)")
class TestAPKeepTumDifferential(unittest.TestCase):
    """ FaVe+APKeep vs FaVe+NetPlumber on the wl_tum stateful firewall. """

    @classmethod
    def setUpClass(cls):
        import apkeep_tum_diff as diff
        cls.diff = diff
        cls.apkeep = diff._pairs(diff.compute_matrix("apkeep"))  # in-process
        with tempfile.TemporaryDirectory(prefix="tum_np_") as tmp:
            cls.netplumber = diff._pairs(
                diff._emit_worker("netplumber", os.path.join(tmp, "np.json")))

    def test_reachability_matches_netplumber(self):
        over = self.apkeep - self.netplumber
        under = self.netplumber - self.apkeep
        self.assertEqual(over, set(),
                         "APKeep over-approximates wl_tum (reachable, NP drops): %s" % sorted(over))
        self.assertEqual(under, set(),
                         "APKeep under-approximates wl_tum (NP reaches, APKeep drops): %s" % sorted(under))
        self.assertEqual(self.apkeep, self.netplumber,
                         "APKeep and NetPlumber disagree on wl_tum reachability")


if __name__ == '__main__':
    unittest.main()
