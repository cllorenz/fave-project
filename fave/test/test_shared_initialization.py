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
        from bench import incremental_run
        prefix = self.WORKLOADS[0]
        self._inputs(prefix)
        out = tempfile.mkdtemp(prefix='shared_init_')
        self.addCleanup(shutil.rmtree, out, True)
        self.assertEqual(incremental_run.main(
            [prefix, '--engine', self.ENGINE, '--stream', 's2', '--fraction', '0.2',
             '--limit-updates', '3', '--cell-dir', out]), 0)
        with open(os.path.join(out, 'head.json')) as raw:
            head = json.load(raw)
        self.assertEqual(sorted(head['phases']),
                         ['t_build_s', 't_check_s', 't_footprint_s', 't_load_s', 't_start_s'])
        self.assertAlmostEqual(head['build_and_first_check_s'],
                               sum(v for k, v in head['phases'].items() if k != 't_start_s'))


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
