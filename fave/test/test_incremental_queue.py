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
import sys
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

    def test_an_alone_cell_takes_a_margin_not_a_limit(self):
        """ A cell with `limit-rss-margin` gets the margin and no
        `--limit-rss`, not even the queue's: incremental_cell.py derives its
        limit from the memory available at its start (the k = 1 trial). """
        saved = dict(q.LIMITS)
        self.addCleanup(q.LIMITS.update, saved)
        q.LIMITS.update({'limit-rss': 32768, 'memory-floor': 2000})
        argv = q.command(_cell('k1', alone=True, **{'limit-rss-margin': 2048,
                                                     'memory-floor': 0}),
                         self.out, 'py')
        self.assertNotIn('--limit-rss', argv)
        self.assertEqual(argv[argv.index('--limit-rss-margin') + 1], '2048')
        self.assertEqual(argv[argv.index('--memory-floor') + 1], '0')
        self.assertNotIn('--alone', argv)

    def test_a_machine_stop_is_listed_not_rerun(self):
        self.assertIn('machine_stop', q.FLAGGED)
        self._result('m', 'machine_stop')
        self.assertEqual(q.plan([_cell('m')], self.out), [])



_FAKE_CELL = r"""
import json, os, sys, time
out = sys.argv[1]
d = os.path.join(out, 'rep01')
os.makedirs(d, exist_ok=True)
t0 = time.time()
time.sleep(0.6)
with open(os.path.join(d, 'cell.json'), 'w') as handle:
    json.dump({'outcome': 'measured', 'cpus': sorted(os.sched_getaffinity(0)),
               'gc_threads': os.environ.get('FAVE_JVM_GC_THREADS'),
               't0': t0, 't1': time.time()}, handle)
"""


class TestPinnedRun(unittest.TestCase):
    """ INCREMENTAL_PLAN.md D17.8: parallel cells on disjoint cores, a JVM's
    collector sized to them; an `alone` cell runs with nothing beside it. """

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix='incq_pin_')
        self.addCleanup(shutil.rmtree, self.out, True)
        saved = q.command
        self.addCleanup(setattr, q, 'command', saved)
        q.command = lambda cell, out_dir, python: [
            sys.executable, '-c', _FAKE_CELL, os.path.join(out_dir, cell['name'])]

    def _cells(self):
        got = {}
        for name in os.listdir(self.out):
            path = os.path.join(self.out, name, 'rep01', 'cell.json')
            if os.path.exists(path):
                with open(path) as raw:
                    got[name] = json.load(raw)
        return got

    def test_core_groups_are_disjoint_and_equal(self):
        groups = q.core_groups(4, list(range(16)))
        self.assertEqual([len(g) for g in groups], [4, 4, 4, 4])
        self.assertEqual(sorted(sum(groups, [])), list(range(16)))
        self.assertEqual(q.pinned(['x'], [2, 3]), ['taskset', '-c', '2,3', 'x'])
        self.assertEqual(q.pinned(['x'], None), ['x'])

    def test_parallel_cells_run_on_disjoint_cores(self):
        if len(os.sched_getaffinity(0)) < 2:
            self.skipTest("one core")
        cells = [_cell('c%d' % i) for i in range(4)]
        q.run(cells, self.out, 2, 10 ** 6, sys.executable, lambda _l: None, pin=True)
        got = self._cells()
        self.assertEqual(len(got), 4)
        for rec in got.values():
            self.assertEqual(int(rec['gc_threads']), len(rec['cpus']))
        # cells that overlapped in time had disjoint cores
        recs = list(got.values())
        for i, a in enumerate(recs):
            for b in recs[i + 1:]:
                if a['t0'] < b['t1'] and b['t0'] < a['t1']:
                    self.assertFalse(set(a['cpus']) & set(b['cpus']))

    def test_an_alone_cell_runs_alone_and_unpinned(self):
        cells = [_cell('a', alone=True, est_h=9), _cell('b'), _cell('c')]
        q.run(cells, self.out, 2, 10 ** 6, sys.executable, lambda _l: None, pin=True)
        got = self._cells()
        alone = got['a']
        for name in ('b', 'c'):
            other = got[name]
            self.assertFalse(alone['t0'] < other['t1'] and other['t0'] < alone['t1'],
                             "%s ran beside the alone cell" % name)
        self.assertEqual(alone['cpus'], sorted(os.sched_getaffinity(0)))
        self.assertIsNone(alone['gc_threads'])


class TestRecordedCells(unittest.TestCase):
    """ D17.10: a cell with a known result is recorded with its basis, not run. """

    def test_a_recorded_cell_is_written_not_run(self):
        out = tempfile.mkdtemp(prefix='incq_rec_')
        self.addCleanup(shutil.rmtree, out, True)
        cell = _cell('bdd_stanford', recorded={
            'outcome': 'did_not_finish', 'limit_tripped': 'wall',
            'basis': 'V5: no answer within 24 h; the cap is 12 h'})
        started = []
        saved = q.subprocess.Popen
        q.subprocess.Popen = lambda *a, **k: started.append(a) or saved(*a, **k)
        try:
            q.run([cell], out, 2, 10 ** 6, sys.executable, lambda _l: None)
        finally:
            q.subprocess.Popen = saved
        self.assertEqual(started, [])
        with open(os.path.join(out, 'bdd_stanford', 'rep01', 'cell.json')) as raw:
            rec = json.load(raw)
        self.assertEqual((rec['outcome'], rec['recorded'], rec['limit_tripped']),
                         ('did_not_finish', True, 'wall'))
        self.assertEqual(q.plan([cell], out), [], "a recorded cell is done")

if __name__ == '__main__':
    unittest.main()
