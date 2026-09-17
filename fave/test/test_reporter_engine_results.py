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

""" AD6_PLAN.md §9.28: the report must render a NON-NetPlumber engine's verdict.

The compliance section of `report.md` was produced ENTIRELY by tailing
net_plumber's own log: `Reporter.run()` parses `DefaultComplianceLogger` lines
into events carrying net_plumber NODE IDS, and `dump_report` resolves those
through `verification_engine.generators`/`.probes` and decodes the condition
with `verification_engine.mapping`.

None of that exists for ad6 or APKeep. Both compute their verdict and hold it in
`get_compliance_results()`, which reached NOTHING -- so a benchmark run on either
would have produced a report saying "No compliance violations have been found"
whatever it actually found. Worse than crashing: the Reporter opens the log at
offset 0, so a STALE `/dev/shm/np/stdout.log` from an earlier NetPlumber run
would have been replayed as this run's verdict.

So: when the engine reports its own results, they are the source of truth, and
the log tail is not consulted. The NetPlumber path is untouched -- it has no
`get_compliance_results` at all.
"""

import os
import tempfile
import unittest

from reporting.reporter import Reporter


class _EngineWithResults:
    """ ad6/APKeep shape: name-based tuples, no NetPlumber node ids, no
    mapping. """

    def __init__(self, results):
        self._results = results

    def get_compliance_results(self):
        return list(self._results)


class _NetPlumberishEngine:
    """ NetPlumber shape: no `get_compliance_results`; the verdict arrives as
    parsed log events instead. """

    def __init__(self):
        self.generators = {'source.a': (0, 1, None)}
        self.probes = {'probe.b': (0, 2, None)}
        self.mapping = None


class _FaVe:
    def __init__(self, engine):
        self.verification_engine = engine
        self.backend = 'ad6'


def _report_text(engine, backend='ad6'):
    fave = _FaVe(engine)
    fave.backend = backend
    reporter = Reporter(fave, None)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'report.md')
        reporter.dump_report(path)
        with open(path) as raw:
            return raw.read()


class TestEngineReportedCompliance(unittest.TestCase):

    def test_a_reporting_engines_violations_reach_the_report(self):
        text = _report_text(_EngineWithResults([
            ('source.internal.ifi', 'probe.admin.ifi', False,
             [{'name': 'related', 'value': '0'}]),
        ]))
        self.assertIn('source.internal.ifi', text)
        self.assertIn('probe.admin.ifi', text)
        self.assertIn('related=0', text)

    def test_no_violations_reads_as_clean_not_as_missing(self):
        text = _report_text(_EngineWithResults([]))
        self.assertIn('No compliance violations have been found', text)

    def test_the_must_reach_polarity_is_rendered(self):
        """ `get_compliance_results` returns `must_reach`; a violation of a
        must-reach check is "does not reach", and of a must-NOT-reach check is
        "reaches". Getting this backwards inverts every line of the report. """
        text = _report_text(_EngineWithResults([
            ('source.a', 'probe.b', True, []),      # must reach, and did not
            ('source.c', 'probe.d', False, []),     # must not reach, and did
        ]))
        self.assertIn('`source.a` does not reach `probe.b`', text)
        self.assertIn('`source.c` reaches `probe.d`', text)

    def test_a_skipped_anomaly_check_is_NOT_reported_as_clean(self):
        """ The benchmark skips the anomaly step for engines that do not
        implement it (§9.28). "No anomalies have been found" would be a verdict
        nobody computed -- exactly the shape of claim the swallowed-exception
        and dropped-condition bugs both produced. """
        text = _report_text(_EngineWithResults([]))
        self.assertNotIn('No anomalies have been found', text)
        self.assertIn('not checked', text.lower())

    def test_the_netplumber_path_is_untouched(self):
        """ An engine that reports nothing of its own still renders from the
        log events, and still says "no violations" when there were none. """
        text = _report_text(_NetPlumberishEngine(), backend='netplumber')
        self.assertIn('No compliance violations have been found', text)


class TestReporterWithoutALog(unittest.TestCase):
    """ `Reporter.__init__` used to `open(np_log)` unconditionally. With no
    net_plumber running there is no log to tail -- and a stale one is worse
    than none, because it would be replayed from offset 0 as this run's
    verdict. """

    def test_a_reporter_with_no_log_constructs_and_drains(self):
        reporter = Reporter(_FaVe(_EngineWithResults([])), None)
        self.assertEqual(reporter.events, [])
        reporter.drain()            # must not hang or raise

    def test_a_missing_log_path_is_not_fatal(self):
        reporter = Reporter(_FaVe(_EngineWithResults([])),
                            '/nonexistent/dir/stdout.log')
        self.assertEqual(reporter.events, [])


if __name__ == '__main__':
    unittest.main()
