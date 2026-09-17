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

""" `GenericBenchmark`'s step contract: which sub-steps may fail quietly and
which may not.

WHY THIS EXISTS. `_compliance` shells out to `bench/compliance_checker.py` with
`os.system()` and DISCARDED the exit status, then logged "checked flow trees."
unconditionally. Found by running wl_example on the ad6 backend (AD6_PLAN.md
§9.28): the checker aborted on the first query -- correctly, refusing a
`protocol` condition the ad6 query path cannot force -- and the benchmark
carried on and produced a report reading **"No compliance violations have been
found"**.

That is the swallowed-sub-step pattern of TODO.md items 1i/1n/1p, in the one
step where it is fatal rather than cosmetic: the compliance verdict is what a
benchmark run is FOR, and "the check could not run" had become indistinguishable
from "the check found nothing". It is NOT backend-specific -- a compliance
checker that crashed under NetPlumber for any reason produced the same clean
report.

`_report` is the deliberate contrast: it already checks its exit codes and is
deliberately non-fatal, because by then the verdict exists and the report is a
presentation artifact.
"""

import logging
import unittest

from bench import generic_benchmark
from bench.generic_benchmark import GenericBenchmark


class _Bench(GenericBenchmark):
    """ Constructed without touching the filesystem beyond what the base class
    already does (it only builds a file-name dict and a logger). """

    def __init__(self, **kwargs):
        logger = logging.getLogger("test_generic_benchmark")
        logger.setLevel(logging.CRITICAL)
        super(_Bench, self).__init__("bench/wl_example", logger=logger, **kwargs)


class _FakeSystem:
    """ Stands in for `os.system`, returning an encoded wait status. """

    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        return self.exit_code << 8          # os.system's WIFEXITED encoding


class _SystemPatch:
    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        self.saved = generic_benchmark.os.system
        generic_benchmark.os.system = self.fake
        return self.fake

    def __exit__(self, *exc):
        generic_benchmark.os.system = self.saved


class TestComplianceFailsLoudly(unittest.TestCase):

    def test_a_failing_compliance_checker_raises(self):
        """ THE POINT OF THIS FILE. A checker that could not run must not read
        as a checker that found nothing. """
        bench = _Bench()
        with _SystemPatch(_FakeSystem(exit_code=1)):
            with self.assertRaises(RuntimeError) as caught:
                bench._compliance()
        self.assertIn("compliance", str(caught.exception).lower())

    def test_a_signalled_compliance_checker_also_raises(self):
        """ `_exit_code` reports a signal as a NEGATIVE number, which is neither
        0 nor anything a naive `== 1` check would catch -- and a compliance
        checker killed by the OOM killer is the realistic way this happens on a
        bench-scale workload. """
        bench = _Bench()
        # A raw status of 9 is WIFSIGNALED (killed by SIGKILL), not WIFEXITED.
        # Patched as a plain function: `os.system` is looked up as an attribute,
        # but a dunder on an INSTANCE is not, so overriding _FakeSystem's
        # __call__ per-instance would never fire.
        calls = []

        def _killed(command):
            calls.append(command)
            return 9

        with _SystemPatch(_killed):
            with self.assertRaises(RuntimeError) as caught:
                bench._compliance()
        self.assertEqual(len(calls), 1)
        self.assertIn("-9", str(caught.exception),
                      "the signal must be reported, not folded into a generic "
                      "failure -- a SIGKILL here usually means the OOM killer")

    def test_a_successful_compliance_checker_does_not_raise(self):
        """ Guards the tests above: a fix that always raised would pass them. """
        bench = _Bench()
        with _SystemPatch(_FakeSystem(exit_code=0)) as fake:
            bench._compliance()
        self.assertEqual(len(fake.commands), 1)
        self.assertIn("compliance_checker.py", fake.commands[0])


class TestTeardownAlwaysRuns(unittest.TestCase):
    """ Making `_compliance` fatal is only safe if the daemons still get
    stopped: `run()` had no `try/finally`, so an aborting step would leave the
    aggregator (and net_plumber) alive, holding their ports and a stale
    /dev/shm/np/aggregator.owner that the next run's barriers would wait on. """

    def _bench_that_fails_at(self, failing_step):
        bench = _Bench()
        for step in ('_pre_preparation', '_preparation', '_post_preparation',
                     '_startup', '_initialization', '_reachability',
                     '_compliance', '_anomalies', '_report', '_dump_fave',
                     '_wait_for_fave'):
            setattr(bench, step, lambda: None)
        bench.torn_down = False

        def _teardown():
            bench.torn_down = True

        bench._teardown = _teardown

        def _boom():
            raise RuntimeError("step failed")

        setattr(bench, failing_step, _boom)
        return bench

    def test_teardown_runs_even_when_compliance_aborts(self):
        bench = self._bench_that_fails_at('_compliance')
        with self.assertRaises(RuntimeError):
            bench.run()
        self.assertTrue(
            bench.torn_down,
            "the aggregator was left running after a failed compliance check")

    def test_the_original_failure_is_not_masked_by_teardown(self):
        """ A teardown that itself raises must not replace the real error. """
        bench = self._bench_that_fails_at('_compliance')

        def _bad_teardown():
            bench.torn_down = True
            raise OSError("stop_fave.sh missing")

        bench._teardown = _bad_teardown
        with self.assertRaises(RuntimeError):
            bench.run()
        self.assertTrue(bench.torn_down)

    def test_a_clean_run_still_tears_down_exactly_once(self):
        bench = self._bench_that_fails_at('_compliance')
        bench._compliance = lambda: None
        calls = []
        bench._teardown = lambda: calls.append(1)
        bench.run()
        self.assertEqual(calls, [1])


class TestBackendSelection(unittest.TestCase):
    """ AD6_PLAN.md §9.28: the harness half of Phase 6's production wiring. """

    def test_the_default_backend_is_netplumber(self):
        self.assertEqual(_Bench().backend, 'netplumber')

    def test_an_unknown_backend_is_refused(self):
        with self.assertRaises(ValueError):
            _Bench(backend='ad')

    def test_the_environment_can_override_the_backend(self):
        """ Every wl_*/benchmark.py constructs its subclass with hardcoded
        arguments, so a constructor parameter alone would reach none of them --
        FAVE_BACKEND is what makes an existing driver runnable on another engine
        without editing it. """
        import os
        saved = os.environ.get('FAVE_BACKEND')
        os.environ['FAVE_BACKEND'] = 'ad6'
        try:
            bench = _Bench()
        finally:
            if saved is None:
                del os.environ['FAVE_BACKEND']
            else:
                os.environ['FAVE_BACKEND'] = saved
        self.assertEqual(bench.backend, 'ad6')

    def test_netplumber_is_started_only_for_the_netplumber_backend(self):
        """ ad6 runs as a subprocess per check_compliance and APKeep in-process,
        so starting net_plumber for them leaves a daemon nothing connects to. """
        for backend, expect_np in (('netplumber', True), ('ad6', False)):
            with self.subTest(backend=backend):
                bench = _Bench(backend=backend)
                bench._wait_for_fave = lambda: None
                with _SystemPatch(_FakeSystem()) as fake:
                    bench._startup()
                started = [c for c in fake.commands if 'start_np.sh' in c]
                self.assertEqual(bool(started), expect_np)

    def test_the_backend_and_its_options_reach_the_aggregator_script(self):
        bench = _Bench(backend='ad6',
                       engine_options='--solver cadical195 --lite-acyclic')
        bench._wait_for_fave = lambda: None
        with _SystemPatch(_FakeSystem()) as fake:
            bench._startup()
        aggr = [c for c in fake.commands if 'start_aggr.sh' in c]
        self.assertEqual(len(aggr), 1)
        self.assertIn('-b ad6', aggr[0])
        self.assertIn('cadical195', aggr[0])
        self.assertIn('--lite-acyclic', aggr[0])

    def test_engine_options_are_shell_quoted(self):
        """ They are one opaque string forwarded to a shell script; an unquoted
        multi-word value would split across `start_aggr.sh`'s own getopts. """
        bench = _Bench(backend='ad6', engine_options='--solver cadical195')
        bench._wait_for_fave = lambda: None
        with _SystemPatch(_FakeSystem()) as fake:
            bench._startup()
        aggr = [c for c in fake.commands if 'start_aggr.sh' in c][0]
        self.assertIn("-X '--solver cadical195'", aggr)


if __name__ == '__main__':
    unittest.main()
