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

""" The shared initialization (INCREMENTAL_PLAN.md D17.2-3) on the real
engines: the model without the generators' links, then the links and the
engine's build, then an untracked first check, then the footprint pass.

* Its verdicts equal those of the path it replaces (everything replayed,
  tracking on, one tracked check), on every engine.
* A lazy engine (VeriFlow-FR, BDD-/NDD-APKeep) is built when the timed
  first check starts, so `t_check_s` holds no build.
* A cell through `bench/incremental_run.py` records the five phases.

`wl_example` (a packet filter, routes, links) and `wl_cloud` (switches);
BDD-APKeep on `wl_example` only (3.24 h to build `wl_cloud`, V5).
"""

import json
import logging
import os
import shutil
import tempfile
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _NDD_JAR, available as apkeep_available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
from veriflow.adapter import VeriFlowAdapter, available as vf_available

_LOG = "test_shared_initialization"


def _logger(level=logging.WARNING):
    log = logging.getLogger(_LOG)
    log.setLevel(level)
    return log


class _Shared(unittest.TestCase):
    __test__ = False
    ENGINE = ''            # incremental_run's --engine name
    WORKLOADS = ('bench/wl_example', 'bench/wl_cloud')

    def make(self):
        raise NotImplementedError

    LAZY = False           # VeriFlow-FR, BDD-/NDD-APKeep: build at the first check

    def built(self, _engine):
        """ Whether a lazy engine has built its model. """
        return False

    def _engine(self):
        engine = self.make()
        if hasattr(engine, 'release'):
            self.addCleanup(engine.release)
        return engine

    def _inputs(self, prefix):
        if not inputs_present(prefix):
            require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        return inc.load_checks(os.path.join(prefix, 'checks.json'))

    def test_the_verdicts_equal_the_old_path(self):
        for prefix in self.WORKLOADS:
            with self.subTest(prefix):
                checks = self._inputs(prefix)
                old_engine = self._engine()
                with InProcessFaVe(old_engine) as fave:
                    fave.replay(prefix)
                    old_engine.track_affected(True)
                    old = inc.VerdictCache(fave, old_engine, checks).full()
                engine = self._engine()
                seen = {}
                phases = inc.Phases()
                record = phases.record

                def probe(name, record=record, engine=engine, seen=seen):
                    if name == 't_check_s' and self.LAZY:
                        seen['built'] = self.built(engine)
                    return record(name)

                phases.record = probe
                with InProcessFaVe(engine) as fave:
                    cache, phases = inc.initialize(fave, engine, prefix, checks,
                                                   phases=phases)
                self.assertEqual(cache.verdict, old)
                self.assertEqual(list(phases.seconds),
                                 ['t_load_s', 't_build_s', 't_check_s', 't_footprint_s'])
                if self.LAZY:
                    self.assertTrue(seen['built'],
                                    "the first check would have built the engine")

    def test_a_cell_records_the_five_phases(self):
        from bench import incremental_cell
        prefix = self.WORKLOADS[0]
        self._inputs(prefix)
        top = tempfile.mkdtemp(prefix='shared_init_')
        self.addCleanup(shutil.rmtree, top, True)
        # through the cell runner, as the queue runs it: V5's sampler and trail
        self.assertEqual(incremental_cell.main(
            [prefix, '--engine', self.ENGINE, '--stream', 's2', '--fraction', '0.2',
             '--limit-updates', '3', '--status-every', '0.5',
             '--out', os.path.join(top, 'cell')]), 0)
        out = os.path.join(top, 'cell', 'rep01')
        with open(os.path.join(out, 'head.json')) as raw:
            head = json.load(raw)
        self.assertEqual(sorted(head['phases']),
                         ['t_build_s', 't_check_s', 't_footprint_s', 't_load_s', 't_start_s'])
        self.assertAlmostEqual(head['build_and_first_check_s'],
                               sum(v for k, v in head['phases'].items() if k != 't_start_s'))
        # D17.5: memory per phase; a JVM engine's live heap after its build
        self.assertEqual(sorted(head['phase_memory']), sorted(head['phases']))
        for name, mem in head['phase_memory'].items():
            self.assertIn('rss_end_mb', mem, name)
        heap = head['phase_memory']['t_build_s'].get('live_heap_mb')
        if self.ENGINE in ('apkeep', 'ndd-apkeep'):
            self.assertGreater(heap, 0)
        else:
            self.assertIsNone(heap)
        # the marks fall inside the cell sampler's trail
        with open(os.path.join(out, 'cell.status.jsonl')) as raw:
            lines = [json.loads(line) for line in raw if line.strip()]
        lines = [line for line in lines if 't_epoch' in line]
        self.assertTrue(lines, "the trail carries no t_epoch")
        start = min(line['t_epoch'] - line['elapsed_s'] for line in lines)
        marks = head['phase_marks']
        self.assertGreaterEqual(min(m[1] for m in marks), start - 1)
        self.assertLessEqual(max(m[2] for m in marks), max(l['t_epoch'] for l in lines) + 1)
        # D17.6-7: verdicts, provenance, the aggregator's log, the GC log
        self.assertTrue(head['verdict_valid'])
        self.assertEqual(head['violations'],
                         sum(1 for v in head['initial_verdicts'].values() if v))
        self.assertTrue(any(path.endswith('checks.json') for path in head['inputs']))
        self.assertTrue(head['artifacts'])
        self.assertIn('engine_options', head)
        with open(os.path.join(out, 'aggregator.log')) as raw:
            self.assertIn('completed task', raw.read())
        with open(os.path.join(out, 'cell.json')) as raw:
            cell = json.load(raw)
        if self.ENGINE in ('apkeep', 'ndd-apkeep'):
            self.assertIn('vlan_rewrite_rules', head['build_metrics'])
            self.assertIsNotNone(cell['gc'], "no GC log for a JVM cell")

    def test_a_from_zero_cell(self):
        """ D17.10: stream `z` -- the initialization without the footprint
        pass, no stream, the same stamps. """
        self.assertEqual(_z_cell(self, self.ENGINE)['phases'].keys(),
                         {'t_start_s', 't_load_s', 't_build_s', 't_check_s'})


def _z_cell(test, engine):
    from bench import incremental_cell
    prefix = 'bench/wl_example'
    if not inputs_present(prefix):
        require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
        test.skipTest("%s inputs not generated" % prefix)
    top = tempfile.mkdtemp(prefix='z_cell_')
    test.addCleanup(shutil.rmtree, top, True)
    test.assertEqual(incremental_cell.main(
        [prefix, '--engine', engine, '--stream', 'z', '--status-every', '0.5',
         '--out', os.path.join(top, 'cell')]), 0)
    with open(os.path.join(top, 'cell', 'rep01', 'head.json')) as raw:
        head = json.load(raw)
    with open(os.path.join(top, 'cell', 'rep01', 'cell.json')) as raw:
        test.assertEqual(json.load(raw)['outcome'], 'measured')
    test.assertTrue(head['verdict_valid'])
    test.assertEqual(head['updates'], 0)
    return head


class TestFromZeroAd6(unittest.TestCase):
    """ ad6 has no update path: the from-zero stream alone (D17.10). """

    def test_a_from_zero_cell(self):
        head = _z_cell(self, 'ad6')
        self.assertEqual((head['engine_options'].get('grounding'),
                          head['engine_options'].get('solver')), ('rank', 'cadical195'))


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestSharedNetPlumber(_Shared):
    __test__ = True
    ENGINE = 'netplumber'

    def make(self):
        return lib_adapter.NetPlumberLibAdapter(_logger())


@require_or_skip(vf_available(), "the VeriFlow-FR library is not built")
class TestSharedVeriFlow(_Shared):
    __test__ = True
    ENGINE = 'veriflow'
    LAZY = True

    def make(self):
        return VeriFlowAdapter(_logger())

    def built(self, engine):
        return engine.net is not None


@require_or_skip(apkeep_available(), "JPype or the APKeep jar is unavailable")
class TestSharedBddAPKeep(_Shared):
    __test__ = True
    ENGINE = 'apkeep'
    LAZY = True
    WORKLOADS = ('bench/wl_example',)

    def make(self):
        return APKeepAdapter(_logger(logging.ERROR), engine='bdd')

    def built(self, engine):
        return engine._built     # pylint: disable=protected-access


@require_or_skip(apkeep_available() and os.path.exists(_NDD_JAR),
                 "JPype, the APKeep jar or the NDD jar is unavailable")
class TestSharedNddAPKeep(_Shared):
    __test__ = True
    ENGINE = 'ndd-apkeep'
    LAZY = True

    def make(self):
        return APKeepAdapter(_logger(logging.ERROR), engine='ndd-apkeep')

    def built(self, engine):
        return engine._built     # pylint: disable=protected-access


if __name__ == '__main__':
    unittest.main()
