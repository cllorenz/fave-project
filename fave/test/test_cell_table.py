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

""" The campaign matrix, and the two ways it was caught misleading.

`MEASUREMENT_RUN_PLAN.md` §9 says where results go and item 31 says what a cell
must carry; nothing read them back into a table until 2026-10-08, so phase A's
matrix was assembled by hand -- which is how a `wl_cloud` row came to say
"refuses (structural)" for a cell that answered.

Both tests here are regressions of a wrong table the generator actually
produced.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'bench', 'campaigns'))
import cell_table                                            # noqa: E402


def _cell(path, **kw):
    base = {'workload': 'wl_cloud', 'outcome': 'measured', 'violations': 1,
            'checks': 71, 'wall_s': 1.0, 'peak_rss_mb': 10}
    base.update(kw)
    with open(path, 'w') as handle:
        json.dump(base, handle)


class TestTheNewestCellWins(unittest.TestCase):
    """ Resolution is by the cell's own `when` stamp, not by argument order.

    It was argument order once, and the first real table it produced was WRONG:
    `--over remeasure --over o1afix` put the older wl_tum cells last, so two of
    them read `error` when the re-measure had already recorded them `measured`.
    A table whose correctness depends on the order of two flags is a table that
    will eventually be built with them the other way round.
    """

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix='base_')
        self.old = tempfile.mkdtemp(prefix='old_')
        self.new = tempfile.mkdtemp(prefix='new_')
        _cell(os.path.join(self.base, 'wl_cloud_np.json'),
              when='2026-10-02T00:00:00+00:00', outcome='error')
        _cell(os.path.join(self.old, 'wl_cloud_np.json'),
              when='2026-10-05T00:00:00+00:00', violations=58)
        _cell(os.path.join(self.new, 'wl_cloud_np.json'),
              when='2026-10-06T00:00:00+00:00', violations=57)

    def test_argument_order_does_not_decide(self):
        for over in ([self.old, self.new], [self.new, self.old]):
            with self.subTest(over=over):
                cells = cell_table.load([self.base] + over)
                self.assertEqual(cells['wl_cloud_np'][0]['violations'], 57)
                self.assertEqual(cells['wl_cloud_np'][1], self.new)

    def test_an_unstamped_cell_sorts_oldest(self):
        """ A result with no `when` predates the harness that stamps one, so it
        must never displace a stamped cell. """
        _cell(os.path.join(self.old, 'wl_cloud_np.json'), violations=99)
        cells = cell_table.load([self.base, self.old, self.new])
        self.assertEqual(cells['wl_cloud_np'][0]['violations'], 57)


class TestADuplicatedViolationLineIsFlagged(unittest.TestCase):
    """ `cell_metrics.violations` counts report LINES. NetPlumber emits one per
    witnessing header space, and HSA's union-of-wildcards is not canonical, so
    one violated check can be witnessed twice: wl_cloud x np scored 58 where
    every other engine scored 57, and that read as a four-against-one ENGINE
    disagreement until 2026-10-07.

    The table flags it rather than silently correcting it: changing the metric
    would move recorded numbers across the campaign and is the owner's call.
    """

    def test_the_distinct_count_is_shown_beside_the_line_count(self):
        d = tempfile.mkdtemp(prefix='dup_')
        _cell(os.path.join(d, 'wl_cloud_np.json'), violations=2, checks=71)
        with open(os.path.join(d, 'wl_cloud_np.report.md'), 'w') as handle:
            handle.write('# Report\n\n## Compliance Check\n'
                         '- `source.a` reaches `probe.b` with \n'
                         '- `source.a` reaches `probe.b` with \n'
                         '\n## Anomaly Check\n')
        self.assertEqual(cell_table.distinct_violations(d, 'wl_cloud_np'), 1)

    def test_a_cell_with_no_report_returns_None_rather_than_guessing(self):
        d = tempfile.mkdtemp(prefix='norep_')
        _cell(os.path.join(d, 'wl_cloud_np.json'))
        self.assertIsNone(cell_table.distinct_violations(d, 'wl_cloud_np'))


class TestAVerdictIsNeverPrintedWithoutItsOutcome(unittest.TestCase):

    def test_an_errored_cell_shows_the_outcome_not_the_count(self):
        # `grep -c '^- '` on a missing report returns 0, indistinguishable from
        # "no violations" -- AD6_PLAN.md 9.34.3.
        self.assertEqual(cell_table.verdict(
            {'outcome': 'error', 'violations': 0, 'checks': 71}), 'error')

    def test_a_checkless_workload_shows_a_dash_not_a_zero(self):
        self.assertIn('no checks', cell_table.verdict(
            {'outcome': 'measured', 'violations': 0, 'checks': None}))

    def test_a_did_not_finish_names_the_limit_and_how_far(self):
        text = cell_table.verdict({'outcome': 'did_not_finish',
                                   'limit_tripped': 'wall', 'wall_s': 86400.0,
                                   'violations': None, 'checks': 240})
        self.assertIn('wall', text)
        self.assertIn('24.0 h', text)


if __name__ == '__main__':
    unittest.main()
