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

""" bench/incremental_queue.py: which cells a restart runs, and the command a
cell becomes. Pure; the cells themselves are not run here. """

import json
import os
import shutil
import tempfile
import unittest

from bench import incremental_queue as q


def _cell(name, **kw):
    cell = {'name': name, 'workload': 'bench/wl_ifi', 'engine': 'netplumber',
            'stream': 's1', 'mem_mb': 1000}
    cell.update(kw)
    return cell


class TestQueue(unittest.TestCase):

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix='incq_')
        self.addCleanup(shutil.rmtree, self.out, True)

    def _result(self, name, outcome):
        d = os.path.join(self.out, name, 'rep01')
        os.makedirs(d)
        with open(os.path.join(d, 'cell.json'), 'w') as handle:
            json.dump({'outcome': outcome}, handle)

    def test_results_and_findings_are_not_rerun_interruptions_are(self):
        # the outcomes incremental_cell.py writes (bench/cell_metrics.py OUTCOMES);
        # a wall or memory limit is `did_not_finish`
        for name, outcome in (('m', 'measured'), ('dnf', 'did_not_finish'), ('r', 'refused'),
                              ('e', 'error'), ('o', 'oracle_failed'), ('i', 'interrupted')):
            self._result(name, outcome)
        os.makedirs(os.path.join(self.out, 'half'))      # died with no result
        cells = [_cell(n) for n in ('m', 'dnf', 'r', 'e', 'o', 'i', 'half', 'new')]
        self.assertEqual(sorted(c['name'] for c in q.plan(cells, self.out)),
                         ['half', 'i', 'new'])

    def test_done_outcomes_are_ones_a_cell_writes(self):
        from bench import cell_metrics
        for outcome in q.DONE + q.FLAGGED:
            self.assertIn(outcome, cell_metrics.OUTCOMES
                          + ('oracle_failed', 'refused', 'machine_stop'))

    def test_an_unfinished_cell_is_moved_aside_not_deleted(self):
        self._result('i', 'interrupted')
        away = q.retire(self.out, 'i')
        self.assertFalse(os.path.exists(os.path.join(self.out, 'i')))
        self.assertTrue(os.path.exists(os.path.join(away, 'rep01', 'cell.json')))
        self.assertTrue(away.startswith(os.path.join(self.out, '_interrupted', 'i.')))
        self.assertIsNone(q.retire(self.out, 'new'))

    def test_longest_first(self):
        cells = [_cell('a', est_h=1), _cell('b', est_h=5), _cell('c')]
        self.assertEqual([c['name'] for c in q.plan(cells, self.out)], ['b', 'a', 'c'])

    def test_command(self):
        argv = q.command(_cell('x', footprint='witness,dead-ends', **{'limit-updates': 50},
                               est_h=2), self.out, 'py')
        self.assertEqual(argv[0], 'py')
        self.assertIn('--limit-rss', argv)
        self.assertEqual(argv[argv.index('--limit-rss') + 1], '1000')
        self.assertEqual(argv[argv.index('--footprint') + 1], 'witness,dead-ends')
        self.assertEqual(argv[argv.index('--limit-updates') + 1], '50')
        self.assertNotIn('--est_h', argv)
        self.assertNotIn('--mem_mb', argv)


    def test_the_rss_limit_is_not_the_reservation(self):
        """ INCREMENTAL_PLAN.md D17.5: `mem_mb` packs the queue; the limit is
        the queue's (V5's class), unless the cell sets its own. """
        saved = dict(q.LIMITS)
        self.addCleanup(q.LIMITS.update, saved)
        limit = lambda argv: argv[argv.index('--limit-rss') + 1]
        q.LIMITS.update({'limit-rss': 32768, 'memory-floor': 2000})
        argv = q.command(_cell('x'), self.out, 'py')
        self.assertEqual((limit(argv), argv[argv.index('--memory-floor') + 1]),
                         ('32768', '2000'))
        argv = q.command(_cell('k1', **{'limit-rss': 64000}), self.out, 'py')
        self.assertEqual(limit(argv), '64000')
        self.assertEqual(argv.count('--limit-rss'), 1)

    def test_a_machine_stop_is_listed_not_rerun(self):
        self.assertIn('machine_stop', q.FLAGGED)
        self._result('m', 'machine_stop')
        self.assertEqual(q.plan([_cell('m')], self.out), [])


if __name__ == '__main__':
    unittest.main()
