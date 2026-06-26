#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" Tests for the compliance/anomaly reporter.

The reporter is a log-tailing daemon thread, but its logic is testable without
the thread or a live backend:

  - ``_parse_log_line`` (extracted from ``run()``) turns a tokenised NetPlumber
    log line into an event tuple -- a pure, position-dependent parse.
  - ``_parse_cond`` decodes a header-space bit-vector against a field mapping.
  - ``dump_report`` renders Markdown from ``self.events`` + a ``fave`` facade;
    we drive it with a ``SimpleNamespace`` stand-in and read /dev/null for the
    log file so no thread is started.
"""

import os
import tempfile
import types
import unittest

from reporting.reporter import Reporter, Log, _parse_log_line, _parse_cond
from netplumber.mapping import Mapping


class TestParseLogLine(unittest.TestCase):
    """ Pins the positional NetPlumber-log parse extracted from run(). """

    @staticmethod
    def _compliance(tail):
        # "DefaultComplianceLogger" must be present; from_/to_/cond are read at
        # fixed offsets 16/18/20 (shifted +1 when a '!' negation marker sits at
        # index 16). Pad indices 1..15 with filler.
        return ['DefaultComplianceLogger'] + ['_'] * 15 + tail

    def test_compliance_with_condition(self):
        line = _parse_log_line(self._compliance(['5', '->', '7', '::', 'COND']))
        self.assertEqual(line, (Log.Compliance, False, '5', '7', 'COND'))

    def test_compliance_negated_shifts_indices(self):
        line = _parse_log_line(self._compliance(['!', '5', '->', '7', '::', 'COND']))
        self.assertEqual(line, (Log.Compliance, True, '5', '7', 'COND'))

    def test_compliance_without_condition(self):
        line = _parse_log_line(self._compliance(['5', '->', '7']))
        self.assertEqual(line, (Log.Compliance, False, '5', '7', None))

    def test_anomaly_strips_trailing_paren(self):
        line = _parse_log_line(['DefaultAnomalyLogger'] + ['_'] * 13 + ['42)'])
        self.assertEqual(line, (Log.Anomalies, 42))

    def test_unrelated_line_is_dropped(self):
        self.assertIsNone(_parse_log_line(['some', 'other', 'log', 'line']))


class TestParseCond(unittest.TestCase):
    """ Decodes a condition bit-vector into (field, value) pairs. """

    def setUp(self):
        self.mapping = Mapping()
        self.mapping.extend('related')  # an 8-bit field

    def test_concrete_field_is_decoded(self):
        self.assertEqual(_parse_cond('00000001', self.mapping), [('related', '1')])

    def test_all_wildcard_field_is_skipped(self):
        self.assertEqual(_parse_cond('xxxxxxxx', self.mapping), [])


class _ReporterTestBase(unittest.TestCase):
    """ Builds a Reporter over /dev/null (no thread, no backend). """

    def _reporter(self, engine, models=None):
        fave = types.SimpleNamespace(
            verification_engine=engine, models=models or {}
        )
        # /dev/null is readable; readline() returns '' so run() (if ever
        # started) would just idle -- but these tests never start the thread.
        return Reporter(fave, os.devnull)

    def _render(self, reporter):
        fd, path = tempfile.mkstemp(suffix='.md')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        reporter.dump_report(path)
        with open(path) as ofile:
            return ofile.read()


class TestDumpReportCompliance(_ReporterTestBase):
    """ dump_report renders compliance findings (or their absence). """

    def _engine(self):
        mapping = Mapping()
        mapping.extend('related')
        return types.SimpleNamespace(
            generators={'gen': (0, 5, 'mdl')},   # name -> (idx, sid, model)
            probes={'pr': (0, 7, 'mdl')},        # name -> (idx, pid, model)
            mapping=mapping, rule_ids={}, tables={}
        )

    def test_no_events_reports_clean(self):
        report = self._render(self._reporter(self._engine()))
        self.assertIn('No compliance violations have been found.', report)
        self.assertIn('No anomalies have been found.', report)

    def test_violation_names_source_probe_and_condition(self):
        reporter = self._reporter(self._engine())
        # sid 5 -> 'gen' reaches pid 7 -> 'pr' with related=1
        reporter.events = [(Log.Compliance, False, '5', '7', '00000001')]
        report = self._render(reporter)
        self.assertIn('`gen` reaches `pr`', report)
        self.assertIn('related=1', report)

    def test_negated_violation_reads_does_not_reach(self):
        reporter = self._reporter(self._engine())
        reporter.events = [(Log.Compliance, True, '5', '7', None)]
        report = self._render(reporter)
        self.assertIn('`gen` does not reach `pr`', report)

    def test_mark_compliance_advances_window(self):
        """ mark_compliance() moves the cursor so old events drop out. """
        reporter = self._reporter(self._engine())
        reporter.events = [(Log.Compliance, False, '5', '7', None)]
        reporter.mark_compliance()  # cursor now past the only event
        report = self._render(reporter)
        self.assertIn('No compliance violations have been found.', report)


class TestDumpReportAnomaly(_ReporterTestBase):
    """ dump_report renders shadowed-rule anomalies. """

    def test_fully_shadowed_rule_is_reported(self):
        fave_rid = (1 << 32) + (5 << 12)   # table_id=1, rule_id=5
        rule = types.SimpleNamespace(
            idx=5, raw_line='-A FORWARD -j DROP', raw_line_no=12
        )
        engine = types.SimpleNamespace(
            generators={}, probes={}, mapping=None,
            rule_ids={fave_rid: [99]}, tables={'fw.1': 1}
        )
        models = {'fw': types.SimpleNamespace(tables={'fw.1': [rule]})}
        reporter = self._reporter(engine, models=models)
        reporter.events = [(Log.Anomalies, 99)]

        report = self._render(reporter)
        self.assertIn('shadowed rule at line 12', report)
        self.assertIn('-A FORWARD -j DROP', report)


if __name__ == '__main__':
    unittest.main()
