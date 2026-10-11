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

""" Milestone 2 under the oracle (INCREMENTAL_PLAN.md §8.1): S4, one-line
configuration edits re-sent through the aggregator with stable indices, so
the engine gets only the rules that changed -- on NetPlumber and VeriFlow-FR.
After every edit the selective re-verification must equal a full one; at
checkpoints the full verdicts must equal a from-zero build of the edited
configurations, built without stable indices. Each workload's edits reach a
different modelling engine: wl_example's and wl_up's packet filters, wl_ifi's
router ACLs, wl_cloud's switch tables. wl_tum has no checks; there the edits
are checked for going through, rule by rule. (APKeep: test_incremental_m2_apkeep.py.)
"""

import logging
import tempfile
import unittest

from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, run_s4
from util import incremental as inc
from veriflow.adapter import VeriFlowAdapter, available as vf_available


def _np():
    log = logging.getLogger("test_incremental_m2")
    log.setLevel(logging.WARNING)
    return lib_adapter.NetPlumberLibAdapter(log)


def _vf(footprint=()):
    def make():
        log = logging.getLogger("test_incremental_m2")
        log.setLevel(logging.WARNING)
        return VeriFlowAdapter(log, footprint=footprint)
    return make


def _workload(test, prefix):
    if not inputs_present(prefix):
        test.skipTest("%s inputs not generated" % prefix)
    return prefix


def _changed(test, stats):
    test.assertGreater(stats['verdict_changes'], 0,
                       "no edit changed a verdict: the oracle was not tested")


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestS4NetPlumber(unittest.TestCase):

    def test_wl_example_oracle_at_every_edit(self):
        _changed(self, run_s4(self, _np, _workload(self, 'bench/wl_example'), 30, 1, every=1))

    def test_wl_ifi_router_acls(self):
        _changed(self, run_s4(self, _np, _workload(self, 'bench/wl_ifi'), 30, 1, every=5))

    def test_wl_up_packet_filters(self):
        stats = run_s4(self, _np, _workload(self, 'bench/wl_up'), 6, 1, every=6)
        _changed(self, stats)
        # the floor of a one-line edit is a rule and its shell copy, per edit
        self.assertLessEqual(stats['engine_rules'], 4 * stats['edits'])

    def test_wl_cloud_switch_tables(self):
        _changed(self, run_s4(self, _np, _workload(self, 'bench/wl_cloud'), 80, 1, every=20))

    def test_wl_tum_edits_go_through_rule_by_rule(self):
        from util.in_process_driver import InProcessFaVe
        prefix = 'bench/wl_tum'
        if not inputs_present(prefix, checks=False):
            self.skipTest("%s inputs not generated" % prefix)
        with tempfile.TemporaryDirectory(prefix='s4_') as work, \
                InProcessFaVe(_np(), stable_indices=True) as fave:
            configs = inc.S4Configs(prefix, work)
            fave.replay(configs.zero_prefix())
            for edit in inc.stream_s4(configs, 10, seed=1):
                configs.resend(fave, configs.apply(edit))
                got = fave._agg.update_stats
                # a rule and its shell copies; never the table
                self.assertLessEqual(got['deleted'] + got['inserted'], 8, edit[:3])


@require_or_skip(vf_available(), "libveriflow_fr is not built")
class TestS4VeriFlow(unittest.TestCase):

    def test_wl_example_oracle_at_every_edit(self):
        _changed(self, run_s4(self, _vf(), _workload(self, 'bench/wl_example'), 30, 1, every=1))

    def test_wl_ifi_router_acls(self):
        _changed(self, run_s4(self, _vf(), _workload(self, 'bench/wl_ifi'), 30, 1, every=5))

    def test_wl_ifi_with_the_finer_footprints(self):
        coarse = run_s4(self, _vf(), _workload(self, 'bench/wl_ifi'), 30, 1, every=10)
        both = run_s4(self, _vf(('witness', 'dead-ends')), 'bench/wl_ifi', 30, 1, every=10)
        self.assertEqual(coarse['verdict_changes'], both['verdict_changes'])
        self.assertLess(both['rechecked'], coarse['rechecked'])

    def test_wl_cloud_switch_tables(self):
        _changed(self, run_s4(self, _vf(), _workload(self, 'bench/wl_cloud'), 80, 1, every=20))


if __name__ == '__main__':
    unittest.main()
