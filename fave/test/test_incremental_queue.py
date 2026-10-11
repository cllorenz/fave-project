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
        for name, outcome in (('m', 'measured'), ('d', 'deadline'), ('mem', 'memory'),
                              ('e', 'error'), ('o', 'oracle_failed'), ('i', 'interrupted')):
            self._result(name, outcome)
        os.makedirs(os.path.join(self.out, 'half'))      # died with no result
        cells = [_cell(n) for n in ('m', 'd', 'mem', 'e', 'o', 'i', 'half', 'new')]
        self.assertEqual(sorted(c['name'] for c in q.plan(cells, self.out)),
                         ['half', 'i', 'new'])

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


if __name__ == '__main__':
    unittest.main()
