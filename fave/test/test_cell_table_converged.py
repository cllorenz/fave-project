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

""" bench/campaigns/cell_table.py on a converged campaign (INCREMENTAL_PLAN.md
D17.11): every cell's head is a from-zero sample; samples that disagree are
shown, never resolved; a pair without a head shows how it stopped. """

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from bench.campaigns import cell_table


def _head(workload, engine, verdicts, load=1.0):
    return {'workload': workload, 'engine': engine, 'verdict_valid': True,
            'violations': sum(1 for v in verdicts.values() if v), 'checks': len(verdicts),
            'initial_verdicts': verdicts,
            'phases': {'t_load_s': load, 't_build_s': 2.0, 't_check_s': 0.5},
            'phase_memory': {'t_build_s': {'peak_mb': 100}, 't_check_s': {'peak_mb': 120}}}


class TestConvergedTable(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='ctab_')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _cell(self, name, cell, head=None, rep='rep01'):
        d = os.path.join(self.dir, 'cells', name, rep)
        os.makedirs(d)
        with open(os.path.join(d, 'cell.json'), 'w') as out:
            json.dump(cell, out)
        if head is not None:
            with open(os.path.join(d, 'head.json'), 'w') as out:
                json.dump(head, out)

    def _table(self, *flags):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cell_table.main([self.dir] + list(flags))
        return buf.getvalue()

    def test_samples_recorded_stops_and_disagreement(self):
        v = {'a': True, 'b': False}
        self._cell('A_wl_up_netplumber_s1', {'outcome': 'measured'},
                   _head('bench/wl_up', 'netplumber', v, load=1.0))
        self._cell('A_wl_up_netplumber_s2', {'outcome': 'did_not_finish'},
                   _head('bench/wl_up', 'netplumber', v, load=3.0))
        self._cell('A_wl_up_apkeep_s1', {'outcome': 'measured'},
                   _head('bench/wl_up', 'apkeep', v))
        self._cell('Z_wl_i2_apkeep', {'outcome': 'did_not_finish', 'limit_tripped': 'wall',
                                      'recorded': True, 'workload': 'bench/wl_i2/i2-json',
                                      'engine': 'apkeep'})
        self._cell('Z_wl_berkeley_k1_veriflow', {
            'outcome': 'did_not_finish', 'measured': {'limit_tripped': 'rss'},
            'argv': ['run.py', 'x/inputs/wl_berkeley_k1', '--engine', 'veriflow']})
        self._cell('A_wl_cloud_veriflow_s1', {'outcome': 'measured'},
                   _head('bench/wl_cloud', 'veriflow', {'a': True}))
        self._cell('A_wl_cloud_veriflow_s2', {'outcome': 'measured'},
                   _head('bench/wl_cloud', 'veriflow', {'a': False}))
        table = self._table()
        self.assertIn('1/2 (n=2)', table)           # NetPlumber, two samples
        self.assertIn('timeout (recorded)', table)
        self.assertIn('memory stop', table)
        self.assertIn('DISAGREE', table)
        timing = self._table('--timing')
        self.assertIn('load 2 s [1-3]', timing)     # the median of 1 and 3
        agreement = self._table('--agreement')
        self.assertIn('wl_up | BDD-APKeep, NetPlumber | agree on all 2 checks', agreement)

    def test_over_is_refused(self):
        self._cell('A_wl_up_netplumber_s1', {'outcome': 'measured'},
                   _head('bench/wl_up', 'netplumber', {'a': True}))
        with self.assertRaises(SystemExit):
            cell_table.main([self.dir, '--over', self.dir])


    def test_the_results_page_has_its_sections(self):
        from bench.campaigns import campaign_results
        v = {'a': True, 'b': False}
        self._cell('A_wl_up_netplumber_s1', {'outcome': 'measured'},
                   _head('bench/wl_up', 'netplumber', v))
        text = campaign_results.results(self.dir)
        for title in ('1. From zero: verdicts', "2. The engines' agreement",
                      '3. From zero: cost per phase', '5. The streams'):
            self.assertIn(title, text)
        self.assertIn('1/2 (n=1)', text)

if __name__ == '__main__':
    unittest.main()
