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

""" A measured run must not be able to finish having recorded nothing.

`faithful_bdd_measure.py` computes `trend` -- rules, ap_num, the window rates,
every quantity `MEASUREMENT_RUN_PLAN.md` §5.3's decision rule compares a probe
against its 2026-09-26 baseline on -- from the Java-side sampler's JSONL alone.
With no path for it the run still starts, still honours its deadline, still
writes a result file, and records `{"samples": 0}`.

Both V5 probes did exactly that on 2026-10-06: two hours of wall-clock, status
`deadline` as designed, and no way to score P8. The sibling driver
`bench/cloud_bdd_measure.py` had defaulted the path from `--out` all along, so
the two drivers disagreed about whether a caller must ask to be measured -- and
the baselines being compared against carry a profile path, which is what made
the omission invisible from the command line.
"""

import os
import unittest

from bench import cloud_bdd_measure, faithful_bdd_measure


class TestTheProbeTurnsItsProfilerOn(unittest.TestCase):

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ('APKEEP_BUILD_PROFILE', 'APKEEP_BUILD_PROFILE_MS')}
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_the_path_defaults_from_out(self):
        path = faithful_bdd_measure._enable_profile('/tmp/probe_x.json')
        self.assertEqual(path, '/tmp/probe_x.json.profile.jsonl')
        # And it is EXPORTED: the sampler is on the Java side and reads the
        # environment, so returning the path without setting it would record a
        # profile that was never written.
        self.assertEqual(os.environ['APKEEP_BUILD_PROFILE'], path)
        self.assertEqual(os.environ['APKEEP_BUILD_PROFILE_MS'], '30000')

    def test_an_explicit_setting_still_wins(self):
        """ The uncapped invocation in the module's usage block names its own
        path and must keep working. """
        os.environ['APKEEP_BUILD_PROFILE'] = '/tmp/chosen.jsonl'
        os.environ['APKEEP_BUILD_PROFILE_MS'] = '5000'
        self.assertEqual(faithful_bdd_measure._enable_profile('/tmp/p.json'),
                         '/tmp/chosen.jsonl')
        self.assertEqual(os.environ['APKEEP_BUILD_PROFILE_MS'], '5000')

    def test_no_out_means_no_profile_rather_than_a_stray_file(self):
        self.assertIsNone(faithful_bdd_measure._enable_profile(None))
        self.assertNotIn('APKEEP_BUILD_PROFILE', os.environ)

    def test_the_two_bdd_drivers_agree(self):
        """ The asymmetry that caused it: one driver defaulted, the other did
        not, and nothing compared them. """
        for module in (faithful_bdd_measure, cloud_bdd_measure):
            with self.subTest(module=module.__name__):
                source = open(module.__file__).read()
                self.assertIn('.profile.jsonl', source,
                              '%s does not default a profile path from --out; '
                              'a run of it can record samples: 0' % module.__name__)


if __name__ == '__main__':
    unittest.main()
