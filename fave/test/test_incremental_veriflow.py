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

""" Incremental re-verification on VeriFlow-FR, held to its oracle
(INCREMENTAL_PLAN.md §5, §6.3) -- the same streams and assertions as
test_incremental_netplumber.py, through test/incremental_oracle.py.

What decides which checks an update can affect here is a WALK FOOTPRINT, not
the affected ECs: each check's device-local walk records the (table, arrival,
packet set) states it reached -- the set after every rewrite on the way -- and
the ports it emitted on. The affected-EC test, "the check's packet set does not
meet the rule", would be unsound wherever a rewrite carries the set into the
rule, and every router pipeline in the suite rewrites in_port/out_port.

wl_cloud runs a shorter S2 here (5% of its rules): VeriFlow-FR answers a full
re-verification of its 71 checks in ~0.3 s, and the oracle asks one after every
update.
"""

import logging
import unittest

from aggregator.abstract_engine import UpdateRefused
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, run, s1, s2_and_s3
from veriflow.adapter import VeriFlowAdapter, available
from util import incremental as inc


def _make():
    log = logging.getLogger("test_incremental_veriflow")
    log.setLevel(logging.WARNING)
    return VeriFlowAdapter(log)


@require_or_skip(available(), "libveriflow_fr is not built")
class TestIncrementalVeriFlow(unittest.TestCase):

    def _workload(self, prefix):
        if not inputs_present(prefix):
            require_or_skip(False, "%s inputs not generated" % prefix)(
                lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        return prefix

    def test_wl_example_s1_oracle_at_every_update(self):
        run(self, _make, self._workload('bench/wl_example'), s1, every=1)

    def test_wl_example_s2_s3(self):
        run(self, _make, self._workload('bench/wl_example'), s2_and_s3(), every=5)

    def test_wl_ifi_s1(self):
        run(self, _make, self._workload('bench/wl_ifi'), s1, every=20)

    def test_wl_ifi_s2_s3(self):
        run(self, _make, self._workload('bench/wl_ifi'), s2_and_s3(), every=10)

    def test_wl_cloud_s2(self):
        run(self, _make, self._workload('bench/wl_cloud'),
            lambda rules, _links: inc.stream_s2(rules, 0.05, seed=1), every=25)


@require_or_skip(available(), "libveriflow_fr is not built")
class TestRefusals(unittest.TestCase):

    def test_an_update_before_the_build_is_refused(self):
        with self.assertRaises(UpdateRefused):
            _make().delete_rule('n', 'n.1', 0)

    def test_a_rebuild_after_an_update_is_refused(self):
        # The recorded model does not carry the updates, so a rebuild from it
        # would silently drop them.
        from util.in_process_driver import InProcessFaVe
        if not inputs_present('bench/wl_example'):
            self.skipTest("bench/wl_example inputs not generated")
        engine = _make()
        with InProcessFaVe(engine) as fave:
            fave.replay('bench/wl_example')
            engine.build()
            key, _rule = inc.model_rules(fave)[0]
            engine.delete_rule(*key)
            with self.assertRaises(UpdateRefused):
                engine.build(['module.ipv6header.mh.type'])


if __name__ == '__main__':
    unittest.main()
