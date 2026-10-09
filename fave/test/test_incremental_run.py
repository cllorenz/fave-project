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

""" The incremental harness (INCREMENTAL_PLAN.md §5, §7, O3–O5):
`bench/incremental_run.py` writes raw records, `incremental_cell.py` runs it
under stamped limits, `incremental_report.py` derives every statistic from the
records, and `incremental_compare.py` holds engines to the same verdict
changes. The oracle run must catch an engine that under-reports. """

import gzip
import json
import os
import shutil
import tempfile
import unittest

from bench import incremental_cell, incremental_compare, incremental_report
from bench import incremental_table
from bench import incremental_run
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present
from veriflow.adapter import available as veriflow_available

_PREFIX = 'bench/wl_example'
_NP = (lib_adapter.libnetplumber is not None, "libnetplumber is not built")
_VF = (veriflow_available(), "libveriflow_fr is not built")


class _Tmp(unittest.TestCase):

    def setUp(self):
        if not inputs_present(_PREFIX):
            self.skipTest("%s inputs not generated" % _PREFIX)
        self.tmp = tempfile.mkdtemp(prefix='inc_run_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def cell(self, engine, *extra, name=None):
        out = os.path.join(self.tmp, name or engine)
        rc = incremental_cell.main([_PREFIX, '--engine', engine,
                                    '--status-every', '0', '--out', out]
                                   + list(extra))
        return rc, os.path.join(out, 'rep01')

    def summary(self, cell_dir, **kwargs):
        return incremental_report.summarize(
            incremental_report.load_cell(cell_dir), **kwargs)


class TestCell(_Tmp):

    def _check(self, engine):
        rc, rep = self.cell(engine, '--stream', 's2', '--fraction', '0.5',
                            '--seed', '3')
        self.assertEqual(rc, 0)
        with open(os.path.join(rep, 'cell.json')) as handle:
            cell = json.load(handle)
        self.assertEqual(cell['limit_class'], 'dev', "never reportable")
        self.assertIn('machine', cell)
        self.assertEqual(cell['outcome'], 'measured')
        self.assertEqual(cell['limit_tripped'], 'none')
        self.assertEqual(cell['limit_update_s'], 3600.0)
        for raw in ('stream.jsonl.gz', 'updates.jsonl.gz'):
            self.assertTrue(os.path.exists(os.path.join(rep, raw)), raw)
        self.assertFalse(os.path.exists(os.path.join(rep, 'updates.jsonl')))

        records = incremental_report.load_cell(rep)
        self.assertEqual(records['head']['seed'], 3)
        self.assertEqual(len(records['updates']), records['head']['updates'])
        for batch in records['updates']:
            self.assertAlmostEqual(batch['t_update_s'], sum(batch['t_each_s']),
                                   places=3)
            self.assertIsNotNone(batch['affected'])
            for line, old, new in batch['changed']:
                self.assertNotEqual(old, new)

        got = self.summary(rep)
        self.assertEqual(got['ended_by'], 'completed')
        self.assertEqual(got['completed_updates'], got['stream_updates'])
        self.assertEqual(set(got['times_by_op']), {'insert', 'delete'})
        self.assertGreater(got['changed'], 0, "the stream changed nothing")
        self.assertLess(got['selectivity'], 1.0)
        self.assertLessEqual(got['precision'], 1.0)
        return rep

    @require_or_skip(*_NP)
    def test_netplumber(self):
        self._check('netplumber')

    @require_or_skip(*_VF)
    def test_veriflow(self):
        self._check('veriflow')

    @require_or_skip(*_NP)
    def test_batches_cover_the_stream(self):
        _rc, rep = self.cell('netplumber', '--stream', 's3', '--batch', '4')
        got = self.summary(rep)
        batches = incremental_report.load_cell(rep)['updates']
        self.assertEqual(sum(b['n'] for b in batches), got['stream_updates'])
        self.assertTrue(all(b['n'] <= 4 for b in batches))
        self.assertNotIn('times_by_op', got, "per-op only at batch 1")

    @require_or_skip(*_NP)
    def test_repetitions_get_their_own_directories_and_a_spread(self):
        out = os.path.join(self.tmp, 'reps')
        incremental_cell.main([_PREFIX, '--engine', 'netplumber', '--stream',
                               's3', '--repetitions', '2', '--status-every',
                               '0', '--out', out])
        reps = [os.path.join(out, 'rep%02d' % i) for i in (1, 2)]
        summaries = [self.summary(r) for r in reps]
        self.assertEqual([s['stamps']['repetition'] for s in summaries], [1, 2])
        spread = incremental_report.spread(summaries)
        self.assertEqual(spread['median']['n'], 2)

    @require_or_skip(*_NP)
    def test_a_cell_is_never_overwritten(self):
        self.cell('netplumber', '--stream', 's3', name='once')
        with self.assertRaises(SystemExit):
            self.cell('netplumber', '--stream', 's3', name='once')


class TestCrossEngine(_Tmp):

    @require_or_skip(*_NP)
    @require_or_skip(*_VF)
    def test_both_engines_change_the_same_verdicts(self):
        cells = [self.cell(e, '--stream', 's2', '--fraction', '0.5')[1]
                 for e in ('netplumber', 'veriflow')]
        got = incremental_compare.compare(
            [incremental_report.load_cell(c) for c in cells])
        self.assertTrue(got['comparable'])
        self.assertTrue(got['agree'], got)

        # ... and a disagreement is caught: drop one verdict change.
        path = os.path.join(cells[1], 'updates.jsonl.gz')
        with gzip.open(path, 'rt') as handle:
            records = [json.loads(line) for line in handle]
        hit = next(r for r in records if r['changed'])
        hit['changed'] = hit['changed'][1:]
        with gzip.open(path, 'wt') as handle:
            handle.writelines(json.dumps(r) + '\n' for r in records)
        got = incremental_compare.compare(
            [incremental_report.load_cell(c) for c in cells])
        self.assertFalse(got['agree'])
        self.assertEqual(got['disagreeing_batches'], 1)

    @require_or_skip(*_NP)
    def test_different_streams_are_not_comparable(self):
        cells = [self.cell('netplumber', '--stream', 's2', '--seed', str(s),
                           name='seed%d' % s)[1] for s in (1, 2)]
        got = incremental_compare.compare(
            [incremental_report.load_cell(c) for c in cells])
        self.assertFalse(got['comparable'])
        self.assertIn('stream_sha256', got['why'])


class TestTable(_Tmp):

    @require_or_skip(*_NP)
    @require_or_skip(*_VF)
    def test_cells_by_name_and_the_cross_engine_column(self):
        for engine in ('netplumber', 'veriflow'):
            incremental_cell.main([_PREFIX, '--engine', engine, '--stream', 's3',
                                   '--status-every', '0', '--out',
                                   os.path.join(self.tmp, 'wl_example_%s_s3' % engine)])
        rows, checks = incremental_table.tables(incremental_table.collect(self.tmp))
        self.assertEqual({(r['workload'], r['stream'], r['engine']) for r in rows},
                         {('wl_example', 's3', 'netplumber'),
                          ('wl_example', 's3', 'veriflow')})
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0]['agree'])
        self.assertIn('| wl_example | s3 | netplumber |',
                      incremental_table.markdown(rows, checks))


class TestAPKeepCell(unittest.TestCase):
    """ BDD-APKeep through the harness: it records refusals (none on this
    stream) and changes the same verdicts as NetPlumber. """

    @require_or_skip(*_NP)
    def test_wl_ifi_agrees_with_netplumber(self):
        from apkeep.lib_apkeep import available as apkeep_available
        if not apkeep_available():
            self.skipTest("JPype or the APKeep jar is unavailable")
        if not inputs_present('bench/wl_ifi'):
            self.skipTest("bench/wl_ifi inputs not generated")
        tmp = tempfile.mkdtemp(prefix='inc_apkeep_')
        self.addCleanup(shutil.rmtree, tmp, True)
        cells = []
        for engine in ('apkeep', 'netplumber'):
            out = os.path.join(tmp, engine)
            self.assertEqual(incremental_cell.main(
                ['bench/wl_ifi', '--engine', engine, '--stream', 's2',
                 '--fraction', '0.1', '--status-every', '0', '--out', out]), 0)
            cells.append(os.path.join(out, 'rep01'))
        summary = incremental_report.summarize(incremental_report.load_cell(cells[0]))
        self.assertEqual(summary['refused'], 0)
        self.assertGreater(summary['changed'], 0)
        got = incremental_compare.compare(
            [incremental_report.load_cell(c) for c in cells])
        self.assertTrue(got['agree'], got)


class _Blind:
    """ An engine that reports nothing as affected -- the defect the oracle
    exists to catch. """

    def __init__(self, engine):
        self.__dict__['_engine'] = engine

    def __getattr__(self, name):
        return getattr(self._engine, name)

    def __setattr__(self, name, value):
        setattr(self._engine, name, value)

    def take_affected(self):
        self._engine.take_affected()
        return set()


class TestOracleRun(_Tmp):

    @require_or_skip(*_NP)
    def test_a_sound_engine_passes(self):
        rc, rep = self.cell('netplumber', '--stream', 's2', '--fraction', '0.5',
                            '--oracle-sample', '3', '--oracle-every', '5')
        self.assertEqual(rc, 0)
        got = self.summary(rep)
        self.assertTrue(got['oracle']['passed'])
        self.assertGreater(got['oracle']['full_checkpoints'], 1)
        self.assertIsInstance(got['times'], str, "an oracle run reports no times")

    @require_or_skip(*_NP)
    def test_an_engine_that_reports_nothing_fails(self):
        real = incremental_run.make_engine
        def blind(name):
            make = real(name)
            return lambda: _Blind(make())
        incremental_run.make_engine = blind
        self.addCleanup(setattr, incremental_run, 'make_engine', real)
        cell_dir = os.path.join(self.tmp, 'blind')
        rc = incremental_run.main([_PREFIX, '--engine', 'netplumber', '--stream',
                                   's2', '--fraction', '0.5', '--oracle-sample',
                                   '1000', '--cell-dir', cell_dir])
        self.assertEqual(rc, 1)
        got = self.summary(cell_dir)
        self.assertEqual(got['ended_by'], 'oracle_failed')
        self.assertFalse(got['oracle']['passed'])
        self.assertLess(got['completed_updates'], got['stream_updates'],
                        "the failure stops the stream")


class TestReadLines(unittest.TestCase):
    """ What a stopped run leaves must still be readable, and nothing else
    malformed may be read silently. """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='inc_lines_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_a_cut_last_line_is_dropped(self):
        path = os.path.join(self.tmp, 'u.jsonl')
        with open(path, 'w') as handle:
            handle.write('{"a": 1}\n{"a": 2}\n{"a": ')
        self.assertEqual(incremental_report.read_lines(path), [{'a': 1}, {'a': 2}])

    def test_a_gzip_without_its_trailer_is_read(self):
        path = os.path.join(self.tmp, 'u.jsonl')
        with gzip.open(path + '.gz', 'wb') as handle:
            handle.write(b''.join(b'{"a": %d}\n' % i for i in range(1000)))
        with open(path + '.gz', 'rb') as handle:
            data = handle.read()
        with open(path + '.gz', 'wb') as handle:
            handle.write(data[:-8])                  # no CRC/size trailer
        self.assertEqual(len(incremental_report.read_lines(path)), 1000)

    def test_a_bad_line_in_the_middle_raises(self):
        path = os.path.join(self.tmp, 'u.jsonl')
        with open(path, 'w') as handle:
            handle.write('{"a": 1}\nnot json\n{"a": 2}\n')
        with self.assertRaises(ValueError):
            incremental_report.read_lines(path)


if __name__ == '__main__':
    unittest.main()
