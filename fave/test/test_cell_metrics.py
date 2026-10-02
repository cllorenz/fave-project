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

""" The measurement primitives, and the two stamps item 31 asked for.

`bench/cell_metrics.py` was extracted from `bench/deltanet/eval/engine_run.py`
so that the suite-wide runner measures with the same code instead of a second
copy. **The extraction is only safe if it is behaviour-preserving**, so the
first test here re-derives every GC summary and violation count stored in the
committed result directories and requires them to come out identical. That is
34 figures across five campaigns, including the ones `CLOUD_BENCH_PLAN.md`
§2.15 quotes -- if the extraction had changed a parser, this fails.

The rest pin `outcome()`, which is where the stopping-rule discipline lives: a
run the environment killed must NOT be readable as a run that did not finish.
"""

import glob
import json
import os
import unittest

from bench import cell_metrics

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.abspath(os.path.join(_HERE, '..'))
_RESULTS = os.path.join(_FAVE, 'bench', 'deltanet', 'eval')


class TestTheExtractionChangedNothing(unittest.TestCase):
    """ Every stored figure re-derives from the extracted code. """

    def test_stored_gc_and_violations_re_derive(self):
        checked = 0
        for path in sorted(glob.glob(os.path.join(_RESULTS, 'results_*',
                                                  '*.json'))):
            stem = os.path.splitext(path)[0]
            with open(path) as handle:
                stored = json.load(handle)

            gc_log = stem + '.gc.log'
            if stored.get('gc') and os.path.exists(gc_log):
                with self.subTest(file=os.path.basename(path), what='gc'):
                    self.assertEqual(cell_metrics.gc_summary(gc_log),
                                     stored['gc'])
                checked += 1

            report = stem + '.report.md'
            if os.path.exists(report) and stored.get('violations') is not None:
                with open(report) as handle:
                    text = handle.read()
                with self.subTest(file=os.path.basename(path), what='report'):
                    self.assertEqual(len(cell_metrics.violations(text)),
                                     stored['violations'])
                checked += 1

        # Guard against the whole test passing because the glob found nothing
        # -- the failure mode that makes a regression test worthless.
        self.assertGreater(checked, 20,
                           "only %d stored figures were re-derived; the glob "
                           "has probably gone stale" % checked)


class TestTheMachineIsStamped(unittest.TestCase):
    """ Item 31: the limit is fixed "with the machine's description". """

    def test_machine_has_what_sizes_a_run(self):
        described = cell_metrics.machine()
        for key in ('ram_mb', 'swap_mb', 'cores', 'kernel'):
            self.assertIn(key, described)
        self.assertGreater(described['ram_mb'], 0)
        # Swap is in here because the 19 GB box had it and the 32 GB box did
        # not, so the same --memory-floor means different things on the two.
        self.assertGreaterEqual(described['swap_mb'], 0)

    def test_limit_stamps_are_item_31s_five(self):
        stamps = cell_metrics.limit_stamps('v5', 86400, 32768, 'none')
        self.assertEqual(
            set(stamps),
            {'limit_class', 'limit_wall_s', 'limit_rss_mb', 'limit_tripped',
             'machine'})

    def test_an_undeclared_trip_value_is_refused(self):
        # Three-valued on purpose; a fourth spelling would silently become a
        # category no reader of the table knows about.
        with self.assertRaises(AssertionError):
            cell_metrics.limit_stamps('v5', 1, 1, 'oom')


class TestACrashIsNotADidNotFinish(unittest.TestCase):
    """ The distinction the whole stopping-rule discipline rests on. """

    def test_the_environment_killing_a_run_is_not_a_result(self):
        self.assertEqual(cell_metrics.outcome('interrupted', False),
                         'interrupted')

    def test_a_declared_limit_killing_a_run_is_a_result(self):
        self.assertEqual(cell_metrics.outcome('deadline', False),
                         'did_not_finish')
        self.assertEqual(cell_metrics.outcome('memory', False),
                         'did_not_finish')

    def test_a_missing_report_is_an_error_not_a_clean_verdict(self):
        # AD6_PLAN.md §9.34.3: `grep -c '^- ' report.md` on an absent file
        # returns 0, indistinguishable from "no violations". A completed run
        # with no readable verdict must not reach `correct`.
        self.assertEqual(
            cell_metrics.outcome('completed', False, expected_violations=0,
                                 got_violations=0),
            'error')

    def test_without_a_declared_expectation_the_outcome_is_measured(self):
        # This harness will not invent an oracle: `reachable.json` is not one
        # (TODO item 1s), and an all-reachable expectation can only catch
        # under-approximation.
        self.assertEqual(cell_metrics.outcome('completed', True), 'measured')

    def test_a_declared_expectation_adjudicates(self):
        self.assertEqual(
            cell_metrics.outcome('completed', True, 0, 0), 'correct')
        self.assertEqual(
            cell_metrics.outcome('completed', True, 0, 3), 'wrong_verdict')

    def test_every_status_maps_to_a_declared_outcome(self):
        for status in cell_metrics.STATUSES:
            with self.subTest(status=status):
                self.assertIn(cell_metrics.outcome(status, True),
                              cell_metrics.OUTCOMES)


if __name__ == '__main__':
    unittest.main()
