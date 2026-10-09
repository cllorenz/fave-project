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

""" Incremental re-verification on NetPlumber, held to its oracle
(INCREMENTAL_PLAN.md §5, §6.3).

Each test builds a workload through the real aggregator path, then drives an
update stream (S1-S3, §7) directly at the adapter. After EVERY update:

* the selective re-verification -- only the checks on a (source, probe) the
  engine reported as affected -- must leave the cache equal to a FULL
  re-verification of every check on the same engine state;

and at checkpoints:

* the full verdicts must equal a FROM-ZERO build of the current model on a
  fresh engine, which never calls an incremental update.

A stream that never changed a verdict would pass all of that vacuously, so each
test also requires that verdicts changed; and one whose selective re-check asked
as many checks as a full one would prove nothing about selectivity.

wl_cloud's S2 stream is also a regression test: its 130th deletion crashed
NetPlumber (an uninitialised `processed_hs` on a flow created by
re-propagation, node.cc) until 2026-10-09.
"""

import logging
import os
import unittest

from aggregator.abstract_engine import UpdateRefused
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import moved_routes, inputs_present, run, s1, s2_and_s3
from util import incremental as inc


def _logger():
    log = logging.getLogger("test_incremental_netplumber")
    log.setLevel(logging.WARNING)
    return log


def _make():
    return lib_adapter.NetPlumberLibAdapter(_logger())


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestIncrementalNetPlumber(unittest.TestCase):

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
        # Includes routes deleted from and re-inserted into wl_ifi's two
        # declared-LPM tables, each back into the slot it had.
        run(self, _make, self._workload('bench/wl_ifi'), s2_and_s3(), every=10)

    def test_wl_cloud_s2_s3(self):
        run(self, _make, self._workload('bench/wl_cloud'), s2_and_s3(), every=50)


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestRefusals(unittest.TestCase):
    """ What the NetPlumber adapter does not do yet, it refuses. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe
        if not inputs_present('bench/wl_ifi'):
            raise unittest.SkipTest("bench/wl_ifi inputs not generated")
        cls.engine = _make()
        cls.fave = InProcessFaVe(cls.engine)
        cls.fave.replay('bench/wl_ifi')
        cls.models = cls.fave._agg.models

    @classmethod
    def tearDownClass(cls):
        cls.fave.stop()

    def test_an_unknown_rule_cannot_be_deleted(self):
        key, _rule = inc.model_rules(self.fave)[0]
        with self.assertRaises(UpdateRefused):
            self.engine.delete_rule(key[0], key[1], 10**6)

    def test_a_present_rule_cannot_be_inserted_again(self):
        _key, rule = inc.model_rules(self.fave)[0]
        with self.assertRaises(UpdateRefused):
            self.engine.insert_rule(rule)

    def test_pre_and_post_routing_are_refused(self):
        for model in self.models.values():
            for tid in model.tables:
                if tid.endswith(('.pre_routing', '.post_routing')):
                    with self.assertRaises(UpdateRefused):
                        self.engine.delete_rule(model.node, tid, 0)
                    return
        self.skipTest("wl_ifi has no pre/post-routing table")



@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestLpmRoom(unittest.TestCase):
    """ O1: a declared-LPM table places a route by prefix-length band and its
    own index, so a route arriving under an index the build never saw still
    wins exactly where its prefix says. Dense priorities refused this. """

    def test_a_route_moved_to_a_new_index_keeps_every_verdict(self):
        moved_routes(self, _make, 'bench/wl_stanford/stanford-json',
                     'bench/wl_stanford/checks.json',
                     {'topology': 'device_topology.json', 'policies': 'probes.json'},
                     source='source.bbra_rtr', table='mid.bbra_rtr.1', pairs=40)


if __name__ == '__main__':
    unittest.main()
