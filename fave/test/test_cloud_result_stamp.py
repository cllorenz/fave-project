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

from bench.wl_cloud.benchmark import RawDataError, verify_raw
from bench.wl_cloud.cloud_provenance import check_key, parse_violations


_NO_VIOLATIONS = """# Report

## Compliance Check
No compliance violations have been found.

## Anomaly Check
No anomalies have been found.
"""

_VIOLATIONS = """# Report

## Compliance Check
The following compliance violations have been found:

- `source.internet` does not reach `probe.dc1_leaf5_host5`
- `source.internet` reaches `probe.dc4_leaf3_host22` with
    - related=0
    - packet.upper.dport=0000000101001011

## Anomaly Check
No anomalies have been found.
"""

#: The two checks `_VIOLATIONS` reports, as the generator writes them.
_Q01 = 's=source.internet && EF p=probe.dc1_leaf5_host5'
_Q04 = ('! s=source.internet && EF p=probe.dc4_leaf3_host22 '
        '&& f=related:0 && f=!port:331')
#: Query 04's SIBLING complement term, which contradicts the same cell on the
#: protocol instead of the port. Same pair, same direction -- so it is the one
#: check a coarser key would confuse with q04.
_Q04_SIBLING = ('! s=source.internet && EF p=probe.dc4_leaf3_host22 '
                '&& f=related:0 && f=!protocol:tcp')


class TestReadingTheVerdict(unittest.TestCase):

    def test_a_clean_report_names_no_violated_check(self):
        self.assertEqual(parse_violations(_NO_VIOLATIONS), set())

    def test_both_violation_shapes_are_recognised(self):
        """ A violated must-reach check reads "does not reach" and a violated
        must-not-reach one reads "reaches" -- the direction in the line is the
        polarity of the CHECK, not of the finding. Both are violations. """
        violated = parse_violations(_VIOLATIONS)
        self.assertIn(check_key(_Q01), violated)
        self.assertIn(check_key(_Q04), violated)

    def test_a_sibling_complement_term_is_not_confused_with_the_query(self):
        """ The reason a violation is keyed on its condition FIELDS and not on
        the pair alone: `Internet ---> host22.S331` compiles to two
        must-not-reach complement checks over the same pair, and only one of
        them is what the dataset's query 04 asks. Attributing the other one's
        violation to q04 would report a third-party verdict as reproduced (or
        not) on the strength of an expectation we invented. """
        violated = parse_violations(_VIOLATIONS)
        self.assertNotIn(check_key(_Q04_SIBLING), violated)

    def test_an_empty_report_is_not_silently_clean(self):
        """ A run that produced no report at all must not read as "nothing was
        violated" -- AD6_PLAN.md §9.34.3 is exactly that mistake. The caller
        passes '' for a missing file; what makes that safe is not this function
        but `pair_oracle_to_checks`, which refuses a query no check carries.
        Pinned here so the pairing stays the thing that notices. """
        self.assertEqual(parse_violations(''), set())


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
