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

""" What wl_cloud's result stamp reads out of a run.

A stamp that always says "all verdicts reproduced" is worse than no stamp: it
manufactures evidence, and it looks exactly like a real one. The reading of
`report.md` is therefore a function of its own with tests, including the two
report shapes a violation actually takes and the empty case.

The raw-data check is here for the same reason. `verify_raw` is what stands
between a benchmark and the failure mode this workload's scripting exists to
prevent -- a file edited by hand while debugging and then forgotten, so that
every later measurement quietly describes a model nobody meant to build.
"""

import os
import shutil
import tempfile
import unittest

from bench.wl_cloud.benchmark import RawDataError, verify_raw, violated_queries


_NO_VIOLATIONS = """# Report

## Compliance Check
No compliance violations have been found.

## Anomaly Check
No anomalies have been found.
"""

_VIOLATIONS = """# Report

## Compliance Check
The following compliance violations have been found:

- `source.q01` does not reach `probe.dc1_leaf5_host5_rx`
- `source.q04` reaches `probe.dc4_leaf3_host22_rx` with
    - packet.upper.dport=331

## Anomaly Check
No anomalies have been found.
"""


class TestReadingTheVerdict(unittest.TestCase):

    def _report(self, text):
        handle, path = tempfile.mkstemp(suffix='.md')
        os.close(handle)
        self.addCleanup(os.unlink, path)
        with open(path, 'w') as out:
            out.write(text)
        return path

    def test_a_clean_report_names_no_violated_query(self):
        self.assertEqual(violated_queries(self._report(_NO_VIOLATIONS)), set())

    def test_both_violation_shapes_are_recognised(self):
        """ "does not reach" (a sat query that failed) and "reaches ... with"
        (an unsat query that failed) are different lines and both count. """
        self.assertEqual(
            violated_queries(self._report(_VIOLATIONS)), {'q01', 'q04'})

    def test_a_missing_report_is_not_silently_clean(self):
        """ A run that produced no report at all must not read as "nothing was
        violated" -- AD6_PLAN.md §9.34.3 is exactly that mistake. The caller
        checks the file exists; this pins that an absent file yields no
        evidence rather than positive evidence. """
        self.assertEqual(violated_queries('/nonexistent/report.md'), set())


class TestRawDataIntegrity(unittest.TestCase):

    def _raw_dir(self, files, manifest):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, True)
        for name, content in files.items():
            with open(os.path.join(path, name), 'w') as out:
                out.write(content)
        with open(os.path.join(path, 'SHA256SUMS'), 'w') as out:
            out.write(manifest)
        return path

    def test_matching_data_verifies(self):
        # sha256 of "hello\n"
        digest = ('5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03')
        path = self._raw_dir({'a.txt': 'hello\n'}, '%s  a.txt\n' % digest)
        verify_raw(path)                       # must not raise

    def test_an_edited_file_is_refused_and_named(self):
        digest = ('5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03')
        path = self._raw_dir({'a.txt': 'edited\n'}, '%s  a.txt\n' % digest)

        with self.assertRaises(RawDataError) as ctx:
            verify_raw(path)
        self.assertIn('a.txt', str(ctx.exception))

    def test_a_missing_file_is_refused(self):
        digest = ('5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03')
        path = self._raw_dir({}, '%s  gone.txt\n' % digest)

        with self.assertRaises(RawDataError) as ctx:
            verify_raw(path)
        self.assertIn('gone.txt', str(ctx.exception))

    def test_a_missing_manifest_is_refused_rather_than_skipped(self):
        """ No manifest means nothing was checked, which must not read the same
        as "everything checked out". """
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, True)

        with self.assertRaises(RawDataError):
            verify_raw(path)


class TestTheVendoredScenario(unittest.TestCase):
    """ The real thing, against the committed manifest. """

    RAW = 'bench/wl_cloud/cloud-tf'

    @unittest.skipUnless(os.path.isdir('bench/wl_cloud/cloud-tf'),
                         'raw scenario not present')
    def test_the_committed_raw_scenario_matches_its_manifest(self):
        verify_raw(self.RAW)


if __name__ == '__main__':
    unittest.main()
