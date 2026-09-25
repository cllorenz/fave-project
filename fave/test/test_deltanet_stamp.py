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

""" `SOURCE.json`: a generated workload directory records what produced it.

The gap this closes is CLOUD_BENCH_PLAN.md §2.3's. `wl_deltanet` carried a
`FAVE_DELTANET_TRACE` selector whose only occurrence in the tree was its own
definition, and the directory it wrote into recorded neither the trace used nor
that a choice existed -- so "which trace is this?" had no answer short of
re-deriving it. D6 gave each trace its own directory; this is what makes the
directory say so.

Two halves, deliberately in one file: the stamp mechanism is generic
(`bench/input_stamp.py`, tier 1) and is unit-tested here against a temporary
directory, while the Delta-net half asserts that every REGISTERED workload
actually carries one and that it agrees with the registry and with
`SHA256SUMS`. A mechanism that works and is wired to nothing is the failure
this second half exists to catch.
"""

import json
import os
import shutil
import tempfile
import unittest

from bench.deltanet.registry import WORKLOADS, prefix_of
from bench.deltanet.trace import RAW
from bench.input_stamp import StampError, read, sha256, verify, write
from test.backend_gate import require_or_skip


class TestStampMechanism(unittest.TestCase):
    """ `bench/input_stamp.py` on a directory nothing else owns. """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='stamp_test_')
        self.a = os.path.join(self.tmp, 'a.json')
        self.b = os.path.join(self.tmp, 'b.json')
        for path, text in ((self.a, '{"a": 1}\n'), (self.b, '{"b": 2}\n')):
            with open(path, 'w') as handle:
                handle.write(text)
        self.files = {'a': self.a, 'b': self.b}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_fresh_stamp_verifies(self):
        write(self.tmp, 'test', self.files)
        self.assertEqual(verify(self.tmp, self.files), [])

    def test_an_edited_file_is_caught(self):
        write(self.tmp, 'test', self.files)
        with open(self.b, 'w') as handle:
            handle.write('{"b": 3}\n')
        problems = verify(self.tmp, self.files)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('b.json changed since the stamp', problems[0])

    def test_a_deleted_file_is_caught(self):
        write(self.tmp, 'test', self.files)
        os.unlink(self.a)
        problems = verify(self.tmp, self.files)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('now missing', problems[0])

    def test_stamping_an_absent_file_is_refused(self):
        """ Not silently omitted: a stamp that skips is a stamp that lies. """
        self.files['gone'] = os.path.join(self.tmp, 'gone.json')
        with self.assertRaises(StampError) as caught:
            write(self.tmp, 'test', self.files)
        self.assertIn('gone', str(caught.exception))

    def test_an_unstamped_directory_says_so(self):
        with self.assertRaises(StampError) as caught:
            read(self.tmp)
        self.assertIn('SOURCE.json', str(caught.exception))

    def test_a_version_it_does_not_know_is_refused(self):
        write(self.tmp, 'test', self.files)
        path = os.path.join(self.tmp, 'SOURCE.json')
        with open(path) as handle:
            stamp = json.load(handle)
        stamp['version'] = 999
        with open(path, 'w') as handle:
            handle.write(json.dumps(stamp))
        self.assertRaises(StampError, read, self.tmp)

    def test_extra_survives_the_round_trip(self):
        write(self.tmp, 'test', self.files, extra={'trace': 'x.csv'})
        self.assertEqual(read(self.tmp)['trace'], 'x.csv')


@require_or_skip(
    all(os.path.isfile(os.path.join(prefix_of(n), 'SOURCE.json'))
        for n in WORKLOADS),
    "Delta-net workload inputs not generated (run test/gen_deltanet_inputs.sh)")
class TestRegisteredWorkloadsAreStamped(unittest.TestCase):
    """ The mechanism is WIRED, for every workload the registry names. """

    def test_each_workload_names_its_own_trace(self):
        for name, trace in sorted(WORKLOADS.items()):
            self.assertEqual(
                read(prefix_of(name))['trace'], trace,
                "%s is stamped with a trace the registry does not give it, "
                "which is the whole confusion D6 removed" % name)

    def test_the_stamped_digest_is_the_vendored_trace(self):
        """ Names agreeing is not the traces agreeing. """
        for name, trace in sorted(WORKLOADS.items()):
            self.assertEqual(
                read(prefix_of(name))['trace_sha256'],
                sha256(os.path.join(RAW, trace)),
                "%s's stamp records a digest that is not the vendored "
                "%s" % (name, trace))

    def test_the_generated_inputs_still_match_their_stamp(self):
        """ Nothing edited a generated file since it was produced. """
        from bench.deltanet.workload import build
        for name in sorted(WORKLOADS):
            run = build(name)
            self.assertEqual(
                run.check_stamp(), [],
                "%s's inputs no longer match its stamp" % name)

    def test_every_registered_workload_has_a_directory(self):
        for name in sorted(WORKLOADS):
            self.assertTrue(
                os.path.isdir(prefix_of(name)),
                "%s is registered but has no directory -- test.sh and the "
                "input generator both loop over the registry, so this would "
                "SKIP rather than fail, and a skip reads as green" % name)


if __name__ == '__main__':
    unittest.main()
