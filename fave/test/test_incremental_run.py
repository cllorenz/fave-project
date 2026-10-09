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

""" bench/incremental_run.py, the development driver for one incremental
stream (INCREMENTAL_PLAN.md §5, §7): it runs on each engine that implements
updates, records what it promises, and fails when the selective
re-verification misses a changed verdict. """

import json
import os
import tempfile
import unittest

from bench import incremental_run
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present
from veriflow.adapter import available as veriflow_available

_PREFIX = 'bench/wl_example'


class TestIncrementalRun(unittest.TestCase):

    def _run(self, engine, *extra):
        if not inputs_present(_PREFIX):
            self.skipTest("%s inputs not generated" % _PREFIX)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'run.json')
            rc = incremental_run.main([_PREFIX, '--engine', engine,
                                       '--out', out] + list(extra))
            with open(out) as handle:
                return rc, json.load(handle)

    def _check(self, engine):
        rc, rec = self._run(engine, '--stream', 's2', '--fraction', '0.5',
                            '--seed', '3', '--precision')
        self.assertEqual(rc, 0)
        self.assertEqual(rec['limit_class'], 'dev', "never reportable")
        self.assertEqual(rec['seed'], 3)
        self.assertIn('machine', rec)
        self.assertEqual(rec['summary']['missed'], 0)
        self.assertEqual(len(rec['batches']), rec['updates'])
        for batch in rec['batches']:
            self.assertAlmostEqual(batch['t_total_s'],
                                   batch['t_update_s'] + batch['t_recheck_s'], places=6)
        self.assertEqual(set(rec['summary']['by_op']), {'insert', 'delete'})

    @require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
    def test_netplumber(self):
        self._check('netplumber')

    @require_or_skip(veriflow_available(), "libveriflow_fr is not built")
    def test_veriflow(self):
        self._check('veriflow')

    @require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
    def test_batches_cover_the_stream(self):
        _rc, rec = self._run('netplumber', '--stream', 's3', '--batch', '4')
        self.assertEqual(sum(b['size'] for b in rec['batches']), rec['updates'])
        self.assertTrue(all(b['size'] <= 4 for b in rec['batches']))
        self.assertNotIn('by_op', rec['summary'], "per-op only at batch 1")


if __name__ == '__main__':
    unittest.main()
