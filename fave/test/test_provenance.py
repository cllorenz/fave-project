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

""" util/provenance.py and bench/campaign_stamps.py (INCREMENTAL_PLAN.md
D17.7): what a cell and a campaign record they ran, and that a changed
artifact is caught. """

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from bench import campaign_stamps
from util import provenance


class TestProvenance(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='prov_')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, 'w') as out:
            out.write(text)
        return path

    def test_inputs_include_the_configurations_the_topology_names(self):
        config = self._write('fw.rules', '-A FORWARD -j ACCEPT\n')
        self._write('topology.json', json.dumps(
            {'devices': [['fw', 'packet_filter', 1, config, ['p1']]], 'links': []}))
        for name in ('routes.json', 'policies.json', 'sources.json'):
            self._write(name, '{}')
        checks = self._write('checks.json', '[]')
        names = {'topology': 'topology.json', 'routes': 'routes.json',
                 'policies': 'policies.json', 'sources': 'sources.json'}
        got = provenance.inputs(self.dir, names, checks)
        self.assertIn(os.path.relpath(config), got)
        self.assertEqual(got[os.path.relpath(config)],
                         hashlib.sha256(b'-A FORWARD -j ACCEPT\n').hexdigest())
        self.assertEqual(len(got), 6)

    def test_engine_stamps_lift_impl_and_upstream(self):
        got = provenance.engine_stamps({'impl': 'authors+fave', 'upstream': 'X',
                                        'engine': 'bdd'})
        self.assertEqual((got['impl'], got['upstream'], got['engine_options']),
                         ('authors+fave', 'X', {'engine': 'bdd'}))


class TestCampaignStamps(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='stamps_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.jar = os.path.join(self.dir, 'engine.jar')
        with open(self.jar, 'w') as out:
            out.write('v1')

    def test_a_changed_artifact_is_caught(self):
        paths = mock.patch.object(provenance, 'artifact_paths', lambda: [self.jar])
        with paths:
            campaign_dir = os.path.join(self.dir, 'campaign')
            self.assertEqual(campaign_stamps.main(['write', campaign_dir]), 0)
            self.assertEqual(campaign_stamps.check(campaign_dir), [])
            with open(self.jar, 'w') as out:
                out.write('v2')
            changed = campaign_stamps.check(campaign_dir)
        self.assertEqual(len(changed), 1)
        self.assertIn('engine.jar', changed[0])

    def test_a_record_is_not_overwritten(self):
        with mock.patch.object(provenance, 'artifact_paths', lambda: [self.jar]):
            campaign_dir = os.path.join(self.dir, 'campaign')
            campaign_stamps.main(['write', campaign_dir])
            with self.assertRaises(SystemExit):
                campaign_stamps.main(['write', campaign_dir])


if __name__ == '__main__':
    unittest.main()
