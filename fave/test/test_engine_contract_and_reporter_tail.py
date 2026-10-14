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

""" Two small contracts the aggregator leans on.

`AbstractVerificationEngine`'s defaults are the SOUND ones: every model
operation an engine does not implement raises, an update it cannot apply is
REFUSED (`UpdateRefused`, never a silent no-op that would keep answering from
the pre-update model), and "what did the updates affect" defaults to None,
i.e. "unknown, re-verify everything".

`Reporter`'s log tail: `run()` turns net_plumber's stdout into events and
tracks how far it has read, `drain()` blocks until that matches the file size,
and the report's condition rendering accepts every shape an engine hands back.
The tail runs on a real thread over a temporary file -- no net_plumber.
"""

import os
import tempfile
import threading
import types
import unittest

from aggregator.abstract_engine import (
    IMPLS, AbstractVerificationEngine, UpdateRefused
)
from reporting.reporter import Log, Reporter, _render_cond


_MODEL_OPS = (
    'add_generator', 'add_generators_bulk', 'add_link', 'add_links_bulk',
    'add_probe', 'add_rules', 'add_slice', 'add_tables', 'add_wiring',
    'check_anomalies', 'delete_generator', 'delete_probe', 'del_slice',
    'dump_flows', 'dump_flow_trees', 'dump_pipes', 'dump_plumbing_network',
    'remove_link', 'stop'
)


class _Bare(AbstractVerificationEngine):  # pylint: disable=abstract-method
    """ An engine that implements nothing. """


class _Fork(AbstractVerificationEngine):  # pylint: disable=abstract-method
    IMPL = 'authors+fave'
    UPSTREAM = 'deadbeef'


class TestAbstractEngineDefaults(unittest.TestCase):
    """ The base class refuses rather than approximates. """

    def test_every_model_operation_is_unimplemented(self):
        engine = _Bare()
        for name in _MODEL_OPS:
            with self.subTest(op=name):
                with self.assertRaises(NotImplementedError):
                    getattr(engine, name)('any', key='arg')

    def test_updates_are_refused_naming_the_engine(self):
        engine = _Bare()
        calls = (
            ('insert_rule', (object(),)),
            ('delete_rule', ('n', 't', 0)),
            ('set_link', ('a.1', 'b.1', False)),
            ('remove_device', (object(), [])),
        )
        for name, args in calls:
            with self.subTest(op=name):
                with self.assertRaises(UpdateRefused) as ctx:
                    getattr(engine, name)(*args)
                self.assertEqual(
                    str(ctx.exception), '_Bare: %s is not implemented' % name)

    def test_a_refusal_is_still_a_not_implemented_error(self):
        """ Callers that predate UpdateRefused catch NotImplementedError. """
        self.assertTrue(issubclass(UpdateRefused, NotImplementedError))

    def test_affected_set_is_unknown_by_default(self):
        engine = _Bare()
        self.assertIsNone(engine.track_affected(True))
        self.assertIsNone(engine.take_affected())

    def test_provenance_stamp(self):
        self.assertEqual(_Bare().configuration_stamp(), {'impl': None})
        self.assertEqual(
            _Fork().configuration_stamp(),
            {'impl': 'authors+fave', 'upstream': 'deadbeef'})
        self.assertIn(_Fork.IMPL, IMPLS)


def _compliance_line(src, dst, negated=False):
    """ A DefaultComplianceLogger line shaped as `_parse_log_line` indexes it
    (tokens 16/18, shifted by one for a '!'). """
    head = ['t%d' % i for i in range(15)] + ['DefaultComplianceLogger']
    body = (['!'] if negated else []) + [src, '->', dst]
    return ' '.join(head + body) + '\n'


def _anomaly_line(np_rid):
    tokens = ['t%d' % i for i in range(14)] + ['%d)' % np_rid]
    tokens[3] = 'DefaultAnomalyLogger'
    return ' '.join(tokens) + '\n'


class TestReporterTail(unittest.TestCase):
    """ run() parses the log as it grows; drain() waits for it to catch up. """

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.log')
        os.close(fd)
        self.addCleanup(os.unlink, self.path)

    def _append(self, *lines):
        with open(self.path, 'a', encoding='utf-8') as log:
            log.writelines(lines)

    def _start(self):
        reporter = Reporter(types.SimpleNamespace(), self.path)
        thread = threading.Thread(target=reporter.run, daemon=True)
        thread.start()

        def stop():
            reporter.stop()
            thread.join(5)
        self.addCleanup(stop)
        return reporter, thread

    def test_run_collects_reportable_lines_and_drain_waits_for_them(self):
        self._append('unrelated noise\n', _compliance_line('5', '7'))
        reporter, _thread = self._start()
        reporter.drain(poll=0.001)
        self.assertEqual(reporter.consumed, os.path.getsize(self.path))
        self.assertEqual(reporter.events, [(Log.Compliance, False, '5', '7', None)])

        # the tail follows the file as it grows
        self._append(_compliance_line('5', '8', negated=True), _anomaly_line(99))
        reporter.drain(poll=0.001)
        self.assertEqual(reporter.events[1:], [
            (Log.Compliance, True, '5', '8', None), (Log.Anomalies, 99)])

    def test_stop_ends_the_tail_and_closes_the_log(self):
        reporter, thread = self._start()
        reporter.stop()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(reporter.np_log.closed)
        # a stopped tailer never blocks a drain, however far behind it is
        self._append(_compliance_line('1', '2'))
        reporter.drain(poll=0.001)

    def test_drain_returns_when_the_log_disappears(self):
        reporter = Reporter(types.SimpleNamespace(), self.path)
        self.addCleanup(reporter.np_log.close)
        self._append('x' * 10 + '\n')      # behind by 11 bytes, never read
        os.unlink(self.path)
        reporter.drain(poll=0.001)          # returns: nothing to wait for
        open(self.path, 'w', encoding='utf-8').close()        # for the cleanup's unlink

    def test_no_log_means_no_tail(self):
        reporter = Reporter(types.SimpleNamespace(), None)
        self.assertIsNone(reporter.np_log)
        reporter.run()                      # returns at once
        reporter.drain()                    # likewise
        self.assertEqual(reporter.events, [])

    def test_an_absent_log_is_not_fatal(self):
        reporter = Reporter(types.SimpleNamespace(),
                            os.path.join(os.path.dirname(self.path), 'nope', 'x'))
        self.assertIsNone(reporter.np_log)
        self.assertEqual(reporter.consumed, 0)

    def test_mark_anomalies_moves_only_the_anomaly_window(self):
        reporter = Reporter(types.SimpleNamespace(), None)
        reporter.events = [(Log.Anomalies, 1), (Log.Anomalies, 2)]
        reporter.mark_anomalies()
        self.assertEqual((reporter.last_anomalies, reporter.last_compliance), (2, 0))


class TestRenderCond(unittest.TestCase):
    """ Every condition shape an engine reports renders; none aborts. """

    def test_empty_and_none_render_nothing(self):
        self.assertEqual(_render_cond(None), [])
        self.assertEqual(_render_cond([]), [])

    def test_a_string_is_kept_whole(self):
        self.assertEqual(_render_cond('tcp_dst=80'), ['tcp_dst=80'])

    def test_dicts_objects_and_unknowns(self):
        rendered = _render_cond([
            {'name': 'packet.upper.dport', 'value': '80'},
            types.SimpleNamespace(name='packet.ipv4.source', value='10.0.0.1'),
            42,
        ])
        self.assertEqual(rendered, [
            'packet.upper.dport=80', 'packet.ipv4.source=10.0.0.1', '42'])


class TestAnomalyRendering(unittest.TestCase):
    """ A shadowed rule without a source line cannot be shown, and is skipped
    rather than rendered as an empty bullet. """

    def test_a_shadowed_rule_without_raw_line_is_skipped(self):
        fave_rid = (1 << 32) + (5 << 12)
        rule = types.SimpleNamespace(idx=5, raw_line=None, raw_line_no=None)
        fave = types.SimpleNamespace(
            verification_engine=types.SimpleNamespace(
                generators={}, probes={}, mapping=None,
                rule_ids={fave_rid: [99]}, tables={'fw.1': 1}),
            models={'fw': types.SimpleNamespace(tables={'fw.1': [rule]})})
        reporter = Reporter(fave, None)
        reporter.events = [(Log.Anomalies, 99)]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'report.md')
            reporter.dump_report(out)
            with open(out, encoding='utf-8') as rfile:
                report = rfile.read()
        self.assertIn('The following anomalies have been found:', report)
        self.assertNotIn('shadowed rule', report)


if __name__ == '__main__':
    unittest.main()
