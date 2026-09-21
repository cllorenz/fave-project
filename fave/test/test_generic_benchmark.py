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

import os
import shutil
import subprocess
import tempfile
import time
import logging
import unittest

from bench import generic_benchmark
from bench.generic_benchmark import net_plumber_processes, GenericBenchmark


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


class TestLengthAndMappingArePairedInTheDrivers(unittest.TestCase):
    """ AD6_PLAN.md §9.29. `length` and `mapping` are ONE setting.

    `length` pre-sizes net_plumber's vectors (`--hdr-len`, BYTES); `mapping`
    pre-sizes the ADAPTER's own mapping, which is what every vector it builds is
    sized from. Pass only `length` and the engine starts wide while the adapter's
    mapping starts at 0 and grows, so every rule emitted before the mapping
    reaches full width is interpreted against a wider space than it was built
    for -- and reachability collapses SILENTLY.

    Measured on wl_stanford's 240 checks: 165 reachable when paired, 9 when not.
    wl_tum always passed both; wl_stanford and wl_i2 passed only `length`.

    A source check rather than a behavioural one, deliberately: reproducing the
    defect needs a live net_plumber and a full model build (minutes, and 111 MB
    of logs), which is not a `fast`-tier test. What this pins is the INVARIANT,
    at the only place it can be violated. """

    _DRIVERS = ("bench/wl_stanford/benchmark.py", "bench/wl_i2/benchmark.py",
                "bench/wl_tum/benchmark.py")

    def test_every_driver_passing_length_also_passes_mapping(self):
        import os
        import re
        for driver in self._DRIVERS:
            if not os.path.isfile(driver):
                continue
            with self.subTest(driver=driver):
                src = open(driver).read()
                passes_length = re.search(r"^\s*length\s*=\s*length\s*,?\s*$",
                                          src, re.M) is not None
                passes_mapping = re.search(r"^\s*mapping\s*=", src, re.M) is not None
                if passes_length:
                    self.assertTrue(
                        passes_mapping,
                        "%s pre-sizes net_plumber with `length=` but never "
                        "pre-sizes the adapter's mapping -- reachability will "
                        "collapse silently (AD6_PLAN.md §9.29)" % driver)

    def test_the_header_length_is_an_integer_not_a_float(self):
        """ `--hdr-len` is parsed with atoi. Python 3's `/` made `128/8` render
        as "16.0" on the command line -- it happened to survive atoi, but only
        by truncation at the '.'. """
        import os
        import re
        for driver in self._DRIVERS:
            if not os.path.isfile(driver):
                continue
            with self.subTest(driver=driver):
                src = open(driver).read()
                self.assertNotRegex(
                    src, r"\['length'\]\s*/\s*8",
                    "%s computes --hdr-len with true division; use // 8" % driver)


class TestTeardownReportsFailure(unittest.TestCase):
    """ AD6_PLAN.md §9.32: `_teardown` must not claim success when nothing was
    stopped.

    net_plumber has NO independent shutdown path: `stop_fave.sh` talks only to
    the AGGREGATOR, which then calls `verification_engine.stop()`. If the
    aggregator never came up, died, or was killed, the stop request reaches
    nobody and net_plumber survives -- and `_teardown` discarded the exit status
    and logged "fave ordered to stop" regardless.

    That is how the leak went unnoticed: the first wl_i2 attempt aborted because
    the aggregator could not bind (§9.30), teardown ran, `stop_fave.sh` exited 1
    against an absent aggregator, and a net_plumber was orphaned for half an
    hour while the log said it had been stopped.

    NON-FATAL, unlike `_compliance`: teardown runs from a `finally`, and raising
    there would mask the original error. It must be LOUD, not fatal. """

    def test_a_failing_stop_is_reported_not_swallowed(self):
        bench = _Bench()
        messages = []
        bench.logger = type("L", (), {
            "info": lambda _s, m, *a: messages.append(("info", m % a if a else m)),
            "error": lambda _s, m, *a: messages.append(("error", m % a if a else m)),
            "exception": lambda _s, m, *a: messages.append(("exception", m)),
        })()
        with _SystemPatch(_FakeSystem(exit_code=1)):
            bench._teardown()

        errors = [m for lvl, m in messages if lvl == "error"]
        self.assertTrue(errors, "a failed teardown logged nothing at error level")
        self.assertNotIn(
            "fave ordered to stop", [m for _lvl, m in messages],
            "teardown claimed success after stop_fave.sh failed -- this is how "
            "an orphaned net_plumber goes unnoticed")

    def test_teardown_does_not_raise_even_when_stop_fails(self):
        """ It runs from `run()`'s `finally`; raising would replace the real
        error with a cleanup error. """
        bench = _Bench()
        with _SystemPatch(_FakeSystem(exit_code=1)):
            bench._teardown()          # must not raise

    def test_a_successful_stop_still_reports_success(self):
        bench = _Bench()
        messages = []
        bench.logger = type("L", (), {
            "info": lambda _s, m, *a: messages.append(m % a if a else m),
            "error": lambda _s, m, *a: messages.append(m % a if a else m),
            "exception": lambda _s, m, *a: messages.append(m),
        })()
        with _SystemPatch(_FakeSystem(exit_code=0)):
            bench._teardown()
        self.assertIn("fave ordered to stop", messages)


class TestNetPlumberHasAnAggregatorIndependentShutdown(unittest.TestCase):
    """ AD6_PLAN.md §9.32: net_plumber must be stoppable WITHOUT the aggregator.

    Its only shutdown path used to be `stop_fave.sh` -> `aggregator/stop.py` ->
    the aggregator -> `verification_engine.stop()`. An aggregator that never
    started, died, or was killed therefore orphaned net_plumber silently, still
    holding its unix socket and still writing logs -- observed for half an hour
    after the first wl_i2 attempt aborted on the §9.30 socket bug.

    `start_np.sh` now records each pid and `stop_fave.sh` falls back to it when
    the aggregator is unreachable. Pinned as AGREEMENT on the pidfile between
    the two scripts: the writer and the reader drifting apart would restore the
    leak with no other symptom.

    The behaviour itself needs a live net_plumber, so it is verified by hand
    (§9.32.3) rather than here; what this guards is that the mechanism still
    exists and that both halves still point at the same file. """

    def _read(self, name):
        import os
        path = os.path.join("scripts", name)
        return open(path).read() if os.path.isfile(path) else ""

    def test_start_np_records_the_pid(self):
        src = self._read("start_np.sh")
        if not src:
            self.skipTest("scripts/start_np.sh not present")
        self.assertRegex(
            src, r"\$!\s*>>\s*\$\{?DIR\}?/np/np\.pid",
            "start_np.sh must APPEND net_plumber's pid to $DIR/np/np.pid -- "
            "appended, because a multi-threaded benchmark starts one instance "
            "per thread through separate invocations")

    def test_stop_fave_falls_back_to_that_pidfile(self):
        src = self._read("stop_fave.sh")
        if not src:
            self.skipTest("scripts/stop_fave.sh not present")
        self.assertRegex(
            src, r"PIDFILE=\$\{?DIR\}?/np/np\.pid",
            "stop_fave.sh must read the same pidfile start_np.sh writes")

    def test_the_fallback_verifies_the_process_before_killing_it(self):
        """ A stale pidfile would otherwise shoot whatever process inherited
        the number. """
        src = self._read("stop_fave.sh")
        if not src:
            self.skipTest("scripts/stop_fave.sh not present")
        self.assertIn("/comm", src,
                      "the fallback must confirm the pid is still a "
                      "net_plumber before killing it")
        self.assertIn('"net_plumber"', src)


class TestStaleSocketCleanup(unittest.TestCase):
    """ AD6_PLAN.md §9.30: the start scripts must test for a stale unix socket
    with `-S` (IS A SOCKET), never `-s` (SIZE > 0).

    A unix socket is always 0 bytes, so `-s` is never true and the stale socket
    is never removed. After any unclean shutdown the aggregator then fails to
    bind with "Address already in use" and the benchmark reports the far less
    helpful "could not connect to fave" -- which is how this was found, on the
    wl_i2 re-run, after an earlier run had been killed.

    `start_np.sh` has always used `-S`; `start_aggr.sh` had a one-character
    typo. Asserted as AGREEMENT between the two scripts rather than as a literal
    string, so the invariant survives either script being rewritten.

    A source check on purpose: reproducing it needs a leftover socket from a
    killed run, which is not a `fast`-tier fixture. """

    _SCRIPTS = ("scripts/start_aggr.sh", "scripts/start_np.sh")

    def test_start_aggr_waits_before_returning(self):
        """ The aggregator binds its socket only AFTER constructing its engine,
        and `misc/await_fave.py` waits on a FILE LOCK -- so nothing in the chain
        waited for the thing the next step needs. Invisible while engine
        construction was cheap (NetPlumber builds no engine of its own; ad6 is a
        subprocess), and fatal once the default APKeep engine became NDD, whose
        jar load loses the race.

        WHAT it waits for has since moved from the socket to the barrier owner
        file (TODO item 17): the bind and the registration are one statement
        apart, and the socket is what the bind CREATES, so the old gate released
        in between. The behaviour is tested for real in
        `test_start_aggr_gate.py`; this only pins that a bounded wait exists at
        all. """
        src = open('scripts/start_aggr.sh').read()
        self.assertIn('AGGR_WAIT', src,
                      "start_aggr.sh must poll for the aggregator it just "
                      "started, with a bounded timeout")

    def test_the_wait_is_bounded_and_reports_failure(self):
        """ A wait that gives up silently is the swallowed-substep shape this
        file already guards against elsewhere: the benchmark would carry on and
        blame the model. """
        src = open('scripts/start_aggr.sh').read()
        self.assertIn('did not register', src)
        self.assertIn('exit 1', src)

    def test_no_start_script_uses_a_size_test_on_a_socket(self):
        import os
        import re
        for script in self._SCRIPTS:
            if not os.path.isfile(script):
                continue
            with self.subTest(script=script):
                src = open(script).read()
                self.assertNotRegex(
                    src, r"\[\s*-s\s+\$\{?UNIX",
                    "%s tests a unix socket with -s (size > 0), which is never "
                    "true for a socket, so a stale one is never removed "
                    "(AD6_PLAN.md §9.30)" % script)

    def test_both_start_scripts_test_for_a_socket(self):
        import os
        import re
        for script in self._SCRIPTS:
            if not os.path.isfile(script):
                continue
            with self.subTest(script=script):
                src = open(script).read()
                self.assertRegex(
                    src, r"\[\s*-S\s+\$\{?UNIX",
                    "%s must remove a stale unix socket before binding" % script)


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



class TestTeardownAdviceIsStateAware(unittest.TestCase):
    """ A ZOMBIE is not an orphaned backend (TODO item 17).

    `_teardown` used to advise `ps -C net_plumber`, which lists zombies and live
    backends identically. `scripts/start_np.sh` backgrounds net_plumber and
    nothing ever waits on it, so each stopped backend leaves an unreaped entry
    wherever pid 1 does not reap -- the normal case in a container. This box
    showed 85 such entries and ZERO live backends, so a reader following the
    advice would have concluded the exact opposite of the truth.

    Tested with REAL processes rather than a fake /proc: the classification is
    the thing under test, and a fixture would have to fake the very field
    (`/proc/<pid>/stat`) whose parsing is the subtle part.
    """

    @classmethod
    def setUpClass(cls):
        cls.sleep = shutil.which('sleep')

    def setUp(self):
        if not self.sleep:
            self.skipTest("no sleep(1) to impersonate net_plumber with")
        self.tmp = tempfile.mkdtemp(prefix='np_state_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

        # `comm` is the EXECUTABLE's name, so a copy under the right name is
        # indistinguishable from the real thing to the classifier. A shell
        # script would not do -- its `comm` is the interpreter's.
        self.fake = os.path.join(self.tmp, 'net_plumber')
        shutil.copy(self.sleep, self.fake)

    def _spawn(self, seconds):
        proc = subprocess.Popen([self.fake, str(seconds)])  # pylint: disable=consider-using-with
        return proc

    def test_a_live_process_is_reported_live(self):
        proc = self._spawn(30)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)

        for _ in range(100):                 # let it exec into the copy
            live, _zombies = net_plumber_processes()
            if proc.pid in live:
                break
            time.sleep(0.02)

        live, zombies = net_plumber_processes()
        self.assertIn(proc.pid, live)
        self.assertNotIn(proc.pid, zombies)

    def test_an_unreaped_exit_is_reported_as_a_zombie(self):
        """ Popen without wait() leaves exactly the state the container does. """
        proc = self._spawn(0)
        self.addCleanup(proc.wait)

        for _ in range(100):
            _live, zombies = net_plumber_processes()
            if proc.pid in zombies:
                break
            time.sleep(0.02)

        live, zombies = net_plumber_processes()
        self.assertIn(proc.pid, zombies,
                      "an unreaped exit was not recognised as a zombie")
        self.assertNotIn(proc.pid, live)

    def _teardown_message(self):
        bench = _Bench()
        messages = []
        bench.logger = type("L", (), {
            "info": lambda _s, m, *a: messages.append(("info", m % a if a else m)),
            "error": lambda _s, m, *a: messages.append(("error", m % a if a else m)),
            "exception": lambda _s, m, *a: messages.append(("exception", m)),
        })()
        with _SystemPatch(_FakeSystem(exit_code=1)):
            bench._teardown()
        return ' '.join(m for lvl, m in messages if lvl == 'error')

    def test_the_advice_no_longer_leaves_the_reader_to_interpret(self):
        """ It used to say only "a net_plumber MAY still be running" and point
        at a command. The state is knowable here, so it is stated. `ps` may
        still be mentioned -- as an explanation of what the reader will see, not
        as a question handed back to them. """
        message = self._teardown_message()
        self.assertNotIn('may still be running', message)
        self.assertTrue(
            'still RUNNING' in message or 'no net_plumber is running' in message,
            "the teardown does not say whether anything is actually running")

    def test_a_live_backend_is_named_by_pid(self):
        proc = self._spawn(30)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)

        for _ in range(100):
            live, _z = net_plumber_processes()
            if proc.pid in live:
                break
            time.sleep(0.02)

        message = self._teardown_message()
        self.assertIn('still RUNNING', message)
        self.assertIn(str(proc.pid), message,
                      "the reader is told something is running but not which")

    def test_zombies_alone_are_reported_as_nothing_orphaned(self):
        """ The case that was actively misleading: entries in `ps`, none of
        them a backend. """
        proc = self._spawn(0)
        self.addCleanup(proc.wait)

        for _ in range(100):
            live, zombies = net_plumber_processes()
            if proc.pid in zombies:
                break
            time.sleep(0.02)

        live, _z = net_plumber_processes()
        if live:
            self.skipTest("a real net_plumber is running; cannot assert the "
                          "zombies-only wording")

        message = self._teardown_message()
        self.assertIn('no net_plumber is running', message)
        self.assertIn('ZOMBIE', message)
        self.assertIn('not what to kill', message)

if __name__ == '__main__':
    unittest.main()
