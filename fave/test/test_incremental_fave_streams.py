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

""" S1-S3 driven through FaVe, held to the oracle (INCREMENTAL_PLAN.md D14:
every measurement is driven through FaVe). Configuration rule lines change by
re-sending the device, routes by `switch.py` commands, links by `topology.py`
commands (`util.fave_streams`). After every batch the selective
re-verification must equal a full one, and at checkpoints the full verdicts a
from-zero build of the workload's current state
(`test.incremental_oracle.fave_stream`).

`wl_example` has a packet filter's configuration, routes into it and into
switches, and links; `wl_cloud` switches with routes and many links.
BDD-APKeep only on `wl_example`: it takes 3.24 h to build `wl_cloud` (V5).
"""

import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _NDD_JAR, available as apkeep_available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import fave_stream, inputs_present
from veriflow.adapter import VeriFlowAdapter, available as vf_available

_LOG = "test_incremental_fave_streams"


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


class _FaveStreams(unittest.TestCase):
    """ The streams, per engine. `REFUSALS`: APKeep refuses an update that
    would change its element structure (APKEEP_INCREMENTAL_SCOPE.md §7). """
    __test__ = False
    MAKE = None
    REFUSALS = False
    WL_CLOUD = True

    def _run(self, prefix, kind, every, **kw):
        stats = fave_stream(self, self.MAKE, _workload(self, prefix), kind, every,
                            refusals=self.REFUSALS, **kw)
        print("%s %s %s %s:" % (type(self).__name__, prefix, kind, kw),
              {k: (len(v) if isinstance(v, list) else v) for k, v in stats.items()})
        return stats

    def test_wl_example_s1(self):
        self._run('bench/wl_example', 's1', every=4)

    def test_wl_example_s2_in_batches(self):
        self._run('bench/wl_example', 's2', every=1, batch=3, fraction=0.5)

    def test_wl_example_s3(self):
        self._run('bench/wl_example', 's3', every=4)

    def _cloud(self):
        if not self.WL_CLOUD:
            self.skipTest("BDD-APKeep takes 3.24 h to build wl_cloud")
        return 'bench/wl_cloud'

    def test_wl_cloud_s2(self):
        self._run(self._cloud(), 's2', every=25, fraction=0.05)

    def test_wl_cloud_s3_in_batches(self):
        # odd, so a batch ends between a link's down and its up
        self._run(self._cloud(), 's3', every=10, batch=3)


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestFaveStreamsNetPlumber(_FaveStreams):
    __test__ = True
    MAKE = staticmethod(_np)


@require_or_skip(vf_available(), "the VeriFlow-FR library is not built")
class TestFaveStreamsVeriFlow(_FaveStreams):
    __test__ = True
    MAKE = staticmethod(_vf)


@require_or_skip(apkeep_available(), "JPype or the APKeep jar is unavailable")
class TestFaveStreamsBddAPKeep(_FaveStreams):
    __test__ = True
    MAKE = staticmethod(_apkeep('bdd'))
    REFUSALS = True
    WL_CLOUD = False


@require_or_skip(apkeep_available() and os.path.exists(_NDD_JAR),
                 "JPype, the APKeep jar or the NDD jar is unavailable")
class TestFaveStreamsNddAPKeep(_FaveStreams):
    __test__ = True
    MAKE = staticmethod(_apkeep('ndd-apkeep'))
    REFUSALS = True
