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


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestS4Harness(unittest.TestCase):
    """ bench/incremental_run.py --stream s4: the records a cell keeps. """

    def test_records_and_oracle(self):
        import json, os
        from bench import incremental_run
        prefix = _workload(self, 'bench/wl_ifi')
        with tempfile.TemporaryDirectory(prefix='s4_cell_') as cell:
            rc = incremental_run.main([prefix, '--engine', 'netplumber', '--stream', 's4',
                                       '--limit-updates', '12', '--oracle-sample', '10',
                                       '--oracle-every', '6', '--cell-dir', cell])
            self.assertEqual(rc, 0)
            with open(os.path.join(cell, 'end.json')) as raw:
                self.assertEqual(json.load(raw)['status'], 'completed')
            with open(os.path.join(cell, 'updates.jsonl')) as raw:
                records = [json.loads(line) for line in raw]
            self.assertEqual(len(records), 12)
            for r in records:
                for field in ('t_model_s', 't_diff_s', 't_update_s', 't_recheck_s',
                              'deleted', 'inserted', 'windows', 'rechecked', 'changed'):
                    self.assertIn(field, r)
                # one line edited: a rule, or a rule and what it replaces
                self.assertLessEqual(r['deleted'] + r['inserted'], 4)
            with open(os.path.join(cell, 'oracle.jsonl')) as raw:
                full = [json.loads(line) for line in raw if '"full"' in line]
            self.assertEqual(len(full), 2)

    def test_a_workload_without_checks_records_its_updates(self):
        # D13: wl_tum has no check set, so S1-S3 measure the updates alone
        import json, os
        from bench import incremental_run
        if not inputs_present('bench/wl_tum', checks=False):
            self.skipTest("bench/wl_tum inputs not generated")
        with tempfile.TemporaryDirectory(prefix='tum_cell_') as cell:
            rc = incremental_run.main(['bench/wl_tum', '--engine', 'netplumber',
                                       '--stream', 's2', '--limit-updates', '3',
                                       '--cell-dir', cell])
            self.assertEqual(rc, 0)
            with open(os.path.join(cell, 'head.json')) as raw:
                head = json.load(raw)
            self.assertEqual((head['checks'], head['checks_file']), (0, None))
            with open(os.path.join(cell, 'updates.jsonl')) as raw:
                records = [json.loads(line) for line in raw]
            self.assertEqual(len(records), 3)
            self.assertTrue(all(r['rechecked'] == 0 and r['t_update_s'] > 0 for r in records))

    def test_batch_is_one(self):
        from bench import incremental_run
        with self.assertRaises(SystemExit):
            incremental_run.main(['bench/wl_ifi', '--engine', 'netplumber', '--stream',
                                  's4', '--batch', '2', '--cell-dir', '/nonexistent'])


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
