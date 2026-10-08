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

""" VeriFlow-FR's EC census against published figures (VERIFLOW_PLAN.md V2).

On a single field VeriFlow's non-minimal range ECs over the whole space are
the intervals every prefix boundary cuts -- what Delta-net's atoms are -- so
APKeep's Table 3 (NSDI'20, the Delta-netMF column) is a third-party count the
engine must reproduce where the data is the same:

  * Airtel1 and Airtel2: 2,799, the same traces as wl_airtel1/2;
  * Stanford* (IP forwarding alone): 2,283, the same hassel data as
    wl_stanford's declared-LPM tables (3,844 rules; APKeep's Table 1: 3.84e3).

Internet2 is NOT the same data (APKeep: 1.26e5 forwarding rules; wl_i2: 77,451),
so its count is pinned as measured, not compared. So are the multi-field
products -- they are where range ECs explode, and a translation that changes
them should be seen to.

Needs the libveriflow_fr build and the generated inputs; skips without them.
"""

import os
import unittest

from test.backend_gate import require_or_skip
from veriflow.adapter import available

_F = {"topology": "device_topology.json", "policies": "probes.json"}


def _present(prefix):
    return os.path.isfile(os.path.join(prefix, "routes.json"))


@require_or_skip(available(), "libveriflow_fr is not built")
class TestEcCensus(unittest.TestCase):

    def _census(self, prefix, files=None):
        if not _present(prefix):
            raise unittest.SkipTest("%s inputs not generated" % prefix)
        from bench.analysis.veriflow_ec_census import census
        return census(prefix, files)

    def test_airtel_reproduces_apkeep_table3(self):
        for prefix in ("bench/wl_airtel1", "bench/wl_airtel2"):
            res = self._census(prefix)
            self.assertEqual(res["fib"]["ecs"], 2799, prefix)
            self.assertEqual(res["all"]["ecs"], 2799, prefix)

    def test_stanford_ip_reproduces_apkeep_table3(self):
        res = self._census("bench/wl_stanford/stanford-json", _F)
        self.assertEqual(res["fib"]["rules"], 3844)
        self.assertEqual(res["fib"]["ecs"], 2283)
        # Measured 2026-09-29: the multi-field product over all 8,792 rules.
        self.assertEqual(res["all"]["ranges_per_field"], [721, 69, 2444, 3, 73, 2])
        self.assertEqual(res["all"]["ecs"], 721 * 69 * 2444 * 3 * 73 * 2)

    def test_i2_is_pinned_as_measured(self):
        res = self._census("bench/wl_i2/i2-json", _F)
        self.assertEqual(res["fib"]["rules"], 77451)
        self.assertEqual(res["fib"]["ecs"], 16232)
        self.assertEqual(res["all"]["ranges_per_field"], [357, 16232])

    def test_cloud_and_ifi_are_pinned_as_measured(self):
        self.assertEqual(self._census("bench/wl_cloud")["all"]["ranges_per_field"],
                         [30, 1259, 3, 27, 27])
        self.assertEqual(self._census("bench/wl_ifi")["all"]["ranges_per_field"],
                         [21, 18, 21, 19, 19])


if __name__ == '__main__':
    unittest.main()
