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

""" A re-sent device whose structure changed REPLACES the stored one
(INCREMENTAL_PLAN.md §8.2, D-R6), held to its oracle
(`test.incremental_oracle.replace_each`): each device is re-sent with one
port more, then as it was, and the verdicts must equal a from-zero build of
what was sent. On NetPlumber and ad6; VeriFlow-FR and APKeep, which only
empty a removed device, refuse.
"""

import json
import os
import tempfile
import unittest

from ad6.adapter import available as ad6_available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, replace_each
from test.test_incremental_device_removal import _ad6, _np, _tiny, _vf
from util.barrier import BarrierError
from util.in_process_driver import InProcessFaVe
from veriflow.adapter import available as vf_available


def _np_leaks(engine):
    """ What NetPlumber's own dump holds that the adapter does not know:
    a table no device names, or a link twice. """
    with tempfile.TemporaryDirectory(prefix='plumbing_') as dump:
        engine._lib.dump_plumbing_network(dump)
        tids = {int(f.split('.')[0]) for f in os.listdir(dump)
                if f.endswith('.tf.json')}
        with open(os.path.join(dump, 'topology.json')) as raw:
            links = [(l['src'], l['dst']) for l in json.load(raw)['topology']]
    return sorted(('table', t) for t in tids - set(engine.tables.values())) + \
        sorted(('link twice', l) for l in set(links) if links.count(l) > 1)


class _Replacing(unittest.TestCase):
    """ Not collected itself; each engine's is. """

    __test__ = False

    MAKE = staticmethod(_np)
    LEAKS = staticmethod(_np_leaks)

    def _replace(self, prefix, names=None):
        if not inputs_present(prefix):
            require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        return replace_each(self, self.MAKE, prefix, names=names, leaks=self.LEAKS)

    def test_tiny(self):
        with tempfile.TemporaryDirectory(prefix='replace_tiny_') as work:
            stats = replace_each(self, self.MAKE, _tiny(work), leaks=self.LEAKS)
        self.assertEqual(stats['replaced'], 2)

    def test_wl_example(self):
        self.assertEqual(self._replace('bench/wl_example')['replaced'], 3)


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestReplaceNetPlumber(_Replacing):

    __test__ = True

    def test_wl_ifi(self):
        self.assertEqual(self._replace('bench/wl_ifi')['replaced'], 17)

    def test_wl_cloud(self):
        self.assertEqual(self._replace('bench/wl_cloud')['replaced'], 86)


@require_or_skip(ad6_available(), "the ad6 bridge is missing")
class TestReplaceAd6(_Replacing):
    """ Every ad6 check rebuilds the model, so wl_ifi is a sample. """

    __test__ = True
    MAKE = staticmethod(_ad6)
    LEAKS = None

    def test_wl_ifi_sample(self):
        self.assertEqual(self._replace(
            'bench/wl_ifi', names={'ifi', 'external.ifi'})['replaced'], 2)


@require_or_skip(vf_available(), "libveriflow_fr is not built")
class TestRefusedOnVeriFlow(unittest.TestCase):

    def test_a_structural_resend_is_refused_and_nothing_changes(self):
        with tempfile.TemporaryDirectory(prefix='replace_tiny_') as work, \
                InProcessFaVe(_vf(), stable_indices=True) as fave:
            fave.replay(_tiny(work))
            fave.check_compliance({'probe.p': [['source.s', False, []]]})
            model = fave._agg.models['sw2']
            with self.assertRaises(BarrierError) as ctx:
                fave.resend_device(['sw2', 'switch', 3])
            self.assertIn('cannot replace a device', str(ctx.exception))
            self.assertIs(fave._agg.models['sw2'], model)


if __name__ == '__main__':
    unittest.main()
