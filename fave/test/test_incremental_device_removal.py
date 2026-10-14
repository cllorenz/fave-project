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

""" Removing a device on NetPlumber, held to its oracle (INCREMENTAL_PLAN.md
§8.2): each device of a workload is deleted through the aggregator, with its
links, as one update; the selective re-verification must equal a full one,
the full verdicts must equal a from-zero build of the workload WITHOUT the
device, and adding the device again must bring every verdict back.
(`test.incremental_oracle.remove_each`.)
"""

import json
import logging
import os
import tempfile
import unittest

from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, remove_each
from util.barrier import BarrierError
from util.in_process_driver import InProcessFaVe


def _residue(engine, model):
    """ What NetPlumber -- its own dump, and the adapter's bookkeeping --
    still holds of `model` after a removal: tables, links ending at its
    ports, rule ids, port and link records. """
    tids = {engine.tables[t] for t in model.tables}
    ports = {engine.ports[p] for p in model.ports if p in engine.ports}

    def left():
        with tempfile.TemporaryDirectory(prefix='plumbing_') as dump:
            engine._lib.dump_plumbing_network(dump)
            tables = sorted(f for f in os.listdir(dump) if f.endswith('.tf.json')
                            and int(f.split('.')[0]) in tids)
            with open(os.path.join(dump, 'topology.json')) as raw:
                links = [(l['src'], l['dst']) for l in json.load(raw)['topology']
                         if l['src'] in ports or l['dst'] in ports]
        return tables + links + [
            ('rule_id', k) for k in engine.rule_ids if k >> 32 in tids] + [
            ('port', p) for p in model.ports if p in engine.ports] + [
            ('link', s, d) for s, ds in engine.links.items() for d in ds
            if s in ports or d in ports]
    return left


def _np():
    log = logging.getLogger("test_incremental_device_removal")
    log.setLevel(logging.WARNING)
    return lib_adapter.NetPlumberLibAdapter(log)


# sw1 -> sw2 -> probe, a source at sw1, and a second probe behind sw1 alone,
# so removing sw2 changes one check and leaves the other
_WORKLOAD = {
    'topology.json': {
        'devices': [['sw1', 'switch', 3], ['sw2', 'switch', 2]],
        'links': [['sw1.2', 'sw2.1', False]],
    },
    'routes.json': [
        ['sw1', 1, 1, ['ipv6_dst=2001:db8::1'], ['fd=sw1.2'], []],
        ['sw1', 1, 2, ['ipv6_dst=2001:db8::2'], ['fd=sw1.3'], []],
        ['sw2', 1, 1, ['ipv6_dst=2001:db8::1'], ['fd=sw2.2'], []],
    ],
    'policies.json': {
        'devices': [['probe.p', 'probe', 'universal', None, None, None, None],
                    ['probe.q', 'probe', 'universal', None, None, None, None]],
        'links': [['sw2.2', 'probe.p.1', False], ['sw1.3', 'probe.q.1', False]],
    },
    'sources.json': {
        'devices': [['source.s', 'generator', ['ipv6_src=2001:db8::5']]],
        'links': [['source.s.1', 'sw1.1', False]],
    },
    'checks.json': ['s=source.s && EF p=probe.p', 's=source.s && EF p=probe.q'],
}

def _tiny(work):
    for name, data in _WORKLOAD.items():
        with open(os.path.join(work, name), 'w') as out:
            json.dump(data, out)
    return work


_GATE = require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")


@_GATE
class TestRemoveDevice(unittest.TestCase):
    """ Every device of each workload, removed and added again. Measured
    2026-10-14: wl_example 2 of 3 (pgf is all its probe's test path names),
    wl_ifi 17 of 17, wl_cloud 86 of 86. """

    def _remove(self, prefix):
        if not inputs_present(prefix):
            require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        stats = remove_each(self, _np, prefix, residue=_residue)
        self.assertGreater(stats['verdict_changes'], 0,
                           "no removal changed a verdict: the oracle was not tested")
        return stats

    def test_tiny(self):
        with tempfile.TemporaryDirectory(prefix='removal_tiny_') as work:
            stats = remove_each(self, _np, _tiny(work), residue=_residue)
        self.assertEqual(stats['removed'], 2)
        self.assertGreater(stats['verdict_changes'], 0)

    def test_wl_example(self):
        self.assertEqual(self._remove('bench/wl_example')['skipped'], ['pgf'])

    def test_wl_ifi(self):
        self.assertEqual(self._remove('bench/wl_ifi')['skipped'], [])

    def test_wl_cloud(self):
        self.assertEqual(self._remove('bench/wl_cloud')['skipped'], [])


@_GATE
class TestRefusals(unittest.TestCase):

    def test_an_unknown_device_is_refused_and_nothing_changes(self):
        with tempfile.TemporaryDirectory(prefix='removal_tiny_') as work, \
                InProcessFaVe(_np()) as fave:
            fave.replay(_tiny(work))
            models = dict(fave._agg.models)
            for name, mtype in (('nope', 'switch'), ('sw1', 'packet_filter')):
                with self.subTest(name=name), self.assertRaises(BarrierError):
                    fave.delete_device(name, mtype)
            self.assertEqual(fave._agg.models, models)


if __name__ == '__main__':
    unittest.main()
