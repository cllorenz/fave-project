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

""" Routes deleted and added again through FaVe, held to the oracle
(INCREMENTAL_PLAN.md D14: every measurement is driven through FaVe). The
deletes are `switch.py -d -r` commands, the re-adds `switch.py -a -r`, one
route or a batch of one node's routes per command; the aggregator turns each
into the engine rules the route became (a packet filter's route is two) and
the engine deletes or inserts exactly those. After every command the
selective re-verification must equal a full one, and at checkpoints the full
verdicts a from-zero build of the model the aggregator holds
(`test.incremental_oracle.route_commands`).

`wl_example`'s routes go into packet filters, `wl_cloud`'s into switches.
BDD-APKeep only on `wl_example`: it takes 3.24 h to build `wl_cloud` (V5).
"""

import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _NDD_JAR, available as apkeep_available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, route_commands
from veriflow.adapter import VeriFlowAdapter, available as vf_available

_LOG = "test_incremental_route_commands"


def _np():
    log = logging.getLogger(_LOG)
    log.setLevel(logging.WARNING)
    return lib_adapter.NetPlumberLibAdapter(log)


def _vf():
    log = logging.getLogger(_LOG)
    log.setLevel(logging.WARNING)
    return VeriFlowAdapter(log)


def _apkeep(engine):
    def make():
        log = logging.getLogger(_LOG)
        log.setLevel(logging.ERROR)
        return APKeepAdapter(log, engine=engine)
    return make


def _workload(test, prefix):
    if not inputs_present(prefix):
        require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
        test.skipTest("%s inputs not generated" % prefix)
    return prefix


class _RouteCommands(unittest.TestCase):
    """ The streams, per engine. `refusals`: APKeep refuses an update that
    would change its element structure (APKEEP_INCREMENTAL_SCOPE.md §7). """
    __test__ = False
    MAKE = None
    REFUSALS = False
    WL_CLOUD = True

    def _run(self, prefix, fraction, batch, every):
        stats = route_commands(self, self.MAKE, _workload(self, prefix), fraction,
                               seed=1, batch=batch, every=every,
                               refusals=self.REFUSALS)
        print("%s %s batch %d:" % (type(self).__name__, prefix, batch),
              {k: (len(v) if isinstance(v, list) else v) for k, v in stats.items()})
        return stats

    def test_wl_example_every_route_one_by_one(self):
        stats = self._run('bench/wl_example', 1.0, batch=1, every=1)
        self.assertEqual((stats['routes'], stats['commands']), (7, 14))

    def test_wl_example_every_route_in_batches(self):
        stats = self._run('bench/wl_example', 1.0, batch=3, every=1)
        self.assertEqual(stats['routes'], 7)
        self.assertLess(stats['commands'], 14)

    def test_wl_cloud_one_by_one(self):
        if not self.WL_CLOUD:
            self.skipTest("BDD-APKeep takes 3.24 h to build wl_cloud")
        self._run('bench/wl_cloud', 0.05, batch=1, every=25)

    def test_wl_cloud_in_batches(self):
        if not self.WL_CLOUD:
            self.skipTest("BDD-APKeep takes 3.24 h to build wl_cloud")
        stats = self._run('bench/wl_cloud', 0.05, batch=10, every=5)
        self.assertLess(stats['commands'], 2 * stats['routes'])


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestRouteCommandsNetPlumber(_RouteCommands):
    __test__ = True
    MAKE = staticmethod(_np)


@require_or_skip(vf_available(), "the VeriFlow-FR library is not built")
class TestRouteCommandsVeriFlow(_RouteCommands):
    __test__ = True
    MAKE = staticmethod(_vf)


@require_or_skip(apkeep_available(), "JPype or the APKeep jar is unavailable")
class TestRouteCommandsBddAPKeep(_RouteCommands):
    __test__ = True
    MAKE = staticmethod(_apkeep('bdd'))
    REFUSALS = True
    WL_CLOUD = False


@require_or_skip(apkeep_available() and os.path.exists(_NDD_JAR),
                 "JPype, the APKeep jar or the NDD jar is unavailable")
class TestRouteCommandsNddAPKeep(_RouteCommands):
    __test__ = True
    MAKE = staticmethod(_apkeep('ndd-apkeep'))
    REFUSALS = True
