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

""" Milestone 2 under the oracle on BDD-APKeep and NDD-APKeep -- S4 as in
test_incremental_m2.py (INCREMENTAL_PLAN.md §8.1), in the own-JVM group with
the other APKeep tests. BDD-APKeep is not run on wl_cloud (a 3.24 h build).
"""

import logging
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _NDD_JAR, available
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, run_s4


def _maker(engine):
    def make():
        log = logging.getLogger("test_incremental_m2_apkeep")
        log.setLevel(logging.ERROR)
        return APKeepAdapter(log, engine=engine)
    return make


class _S4(unittest.TestCase):

    ENGINE = 'bdd'

    def _run(self, prefix, n, every):
        if not inputs_present(prefix):
            self.skipTest("%s inputs not generated" % prefix)
        stats = run_s4(self, _maker(self.ENGINE), prefix, n, 1, every=every)
        self.assertGreater(stats['verdict_changes'], 0,
                           "no edit changed a verdict: the oracle was not tested")
        return stats


@require_or_skip(available(), "the APKeep jar is not built")
class TestS4BddApkeep(_S4):

    def test_wl_example_oracle_at_every_edit(self):
        self._run('bench/wl_example', 30, every=1)

    def test_wl_ifi_router_acls(self):
        self._run('bench/wl_ifi', 30, every=5)


@require_or_skip(available() and __import__('os').path.exists(_NDD_JAR),
                 "the APKeep or NDD jar is not built")
class TestS4NddApkeep(_S4):

    ENGINE = 'ndd-apkeep'

    def test_wl_example_oracle_at_every_edit(self):
        self._run('bench/wl_example', 30, every=1)

    def test_wl_ifi_router_acls(self):
        self._run('bench/wl_ifi', 30, every=5)

    def test_wl_cloud_switch_tables(self):
        self._run('bench/wl_cloud', 80, every=40)


if __name__ == '__main__':
    unittest.main()
