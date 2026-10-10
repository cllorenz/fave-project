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

""" NDD-APKeep from zero (APKEEP_INCREMENTAL_SCOPE.md §4, step 4): APKeep's
own network and elements with NDD's per-field atoms answer every check of a
workload exactly as NDD-flood does -- and as BDD-APKeep does where that
finishes -- check by check, not as a count.

NDD-APKeep is `APKeepAdapter(engine='ndd-apkeep')`: the BDD adapter's
translation and paths, `apkeep.core.Network(name, "ndd")` behind them.
Workloads with generated inputs only; the faithful wl_stanford and wl_i2 are
the ones BDD-APKeep does not finish in 24 h (V5).
"""

import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _NDD_JAR, available
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present
from util import incremental as inc

ndd_available = available() and os.path.isfile(_NDD_JAR)

_HSA = {'topology': 'device_topology.json', 'policies': 'probes.json'}


def _verdicts(engine, prefix, checks_path, files=None):
    """ Every check's verdict; for NDD-APKeep also its molecule invariants
    (every molecule equals its port's predicate, the atom-to-holder map is
    exact) -- verdicts can agree over corrupted molecules, as wl_cloud's did
    while NDD's atomization gave a label shared by two fields one field's
    atoms (ndd/FAVE_CHANGES.md §12). """
    from util.in_process_driver import InProcessFaVe
    log = logging.getLogger("test_ndd_apkeep")
    log.setLevel(logging.ERROR)
    adapter = APKeepAdapter(log, engine=engine)
    checks = inc.load_checks(checks_path)
    with InProcessFaVe(adapter) as fave:
        fave.replay(prefix, files)
        verdicts = inc.VerdictCache(fave, adapter, checks).full()
        if engine == 'ndd-apkeep':
            bad = [str(b) for b in adapter._lib._net.nddPorts().checkInvariants()]
            assert not bad, "%s: %d molecule invariants broken, e.g. %s" % (
                prefix, len(bad), bad[:3])
            adapter._lib.close()       # leave the registry atom splits reach
        return verdicts


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestFromZero(unittest.TestCase):

    def _same(self, prefix, checks_path=None, files=None, engines=('ndd',)):
        checks_path = checks_path or os.path.join(prefix, 'checks.json')
        if not os.path.exists(checks_path) or not (
                files or inputs_present(prefix)):
            require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        mine = _verdicts('ndd-apkeep', prefix, checks_path, files)
        self.assertTrue(mine, "no checks asked")
        for other in engines:
            self.assertEqual(mine, _verdicts(other, prefix, checks_path, files),
                             "%s: NDD-APKeep and %s disagree" % (prefix, other))
        return mine

    def test_wl_example(self):
        self._same('bench/wl_example', engines=('ndd', 'bdd'))

    def test_wl_ifi(self):
        # router ACLs: one packet universe here, ACL division on BDD-APKeep
        verdicts = self._same('bench/wl_ifi', engines=('ndd', 'bdd'))
        self.assertEqual(sum(verdicts.values()), 27)

    def test_wl_cloud(self):
        # NATs rewriting addresses: the rewrite by `exist` on molecules
        verdicts = self._same('bench/wl_cloud')
        self.assertEqual(sum(verdicts.values()), 57)

    def test_wl_stanford_faithful(self):
        # VLAN rewrites and VLAN admission, the model BDD-APKeep does not finish
        if not os.path.exists('bench/wl_stanford/stanford-json/routes.json'):
            self.skipTest("wl_stanford inputs not generated")
        verdicts = self._same('bench/wl_stanford/stanford-json',
                              'bench/wl_stanford/checks.json', _HSA)
        self.assertEqual(sum(verdicts.values()), 75)

    def test_wl_airtel1(self):
        # 39,600 ingress-split destination routes
        self._same('bench/wl_airtel1')


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestStamp(unittest.TestCase):

    def test_ndd_apkeep_is_named_apart(self):
        log = logging.getLogger("test_ndd_apkeep")
        stamp = APKeepAdapter(log, engine='ndd-apkeep').configuration_stamp()
        self.assertEqual(stamp['engine'], 'ndd-apkeep')
        self.assertIn('NDD', stamp['upstream'])
        self.assertIn('apkeep', stamp['upstream'])


if __name__ == '__main__':
    unittest.main()
