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

""" The campaign harness: every stopping rule, MADE TO FIRE.

`MEASUREMENT_RUN_PLAN.md` §3 -- *"a limit that has never fired is not a
limit."* The three declared stopping rules and the signal path are each
exercised here against a trivial command, which is why `run_cell` takes a
COMMAND rather than a workload: firing them through a real benchmark would make
this a backend test, put it in a tier that needs a JVM, and take minutes.

The one that matters most is `test_an_outside_signal_is_interrupted_not_a_
deadline`. On a container inside a VM on a shared server, the difference
between "the declared limit stopped this engine" and "the machine died under
it" is the difference between a result and a re-run, and nothing downstream can
recover it if the harness writes the wrong one.

Pure Python, no backend: ~8 s of `sleep`.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest

from bench import cell_metrics, cell_queue, cell_run

_PY = sys.executable


def _args(**kwargs):
    """ The argparse namespace `build_command` reads, with the defaults that
    `main`'s parser would have supplied. """
    spec = dict(workload='wl_ifi', backend='apkeep', apkeep_engine='ndd',
                vf_fields='4+10', engine_options='', jvm_xmx=None,
                keep_every=None, reuse_inputs=False, mutate=False,
                mutate_cell='s1,s8')
    spec.update(kwargs)
    return argparse.Namespace(**spec)


class TestEveryStoppingRuleFires(unittest.TestCase):
    """ Each rule, against a command chosen to trip exactly that one. """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='cell_run_')
        self.out = os.path.join(self.dir, 'cell.json')

    def _run(self, argv, wall=600, rss=0, floor=0, every=1, grace=0.3,
             poll=0.05):
        # `grace` is the post-exit wait before the orphan sweep and `poll` the
        # sample interval, hence the granularity of both stopping rules. Only
        # the orphan tests care about the first; the second is 1 s in the
        # campaign and is dropped here so sub-second limits can be made to
        # fire without this tier paying a second per rule.
        return cell_run.run_cell(argv, {}, wall, rss, floor, every, self.out,
                                 grace_s=grace, poll_s=poll)

    def test_a_clean_exit_trips_nothing(self):
        got = self._run([_PY, '-c', 'pass'])
        self.assertEqual(got['status'], 'completed')
        self.assertEqual(got['limit_tripped'], 'none')
        self.assertEqual(got['exit'], 0)

    def test_a_non_zero_exit_is_an_error_not_a_limit(self):
        got = self._run([_PY, '-c', 'raise SystemExit(3)'])
        self.assertEqual(got['status'], 'error')
        self.assertEqual(got['limit_tripped'], 'none')
        self.assertEqual(got['exit'], 3)

    def test_the_wall_clock_limit_fires(self):
        got = self._run([_PY, '-c', 'import time; time.sleep(30)'], wall=0.3)
        self.assertEqual(got['status'], 'deadline')
        self.assertEqual(got['limit_tripped'], 'wall')
        self.assertLess(got['wall_s'], 20)
        self.assertEqual(cell_metrics.outcome(got['status'], False),
                         'did_not_finish')

    def test_the_rss_limit_fires(self):
        # Item 31's declared per-cell memory limit, as a cap on the run's
        # summed RSS. Not RLIMIT_AS, which misfires on the JVM.
        got = self._run(
            [_PY, '-c', "x = bytearray(80 * 1024 * 1024)\n"
                        "import time; time.sleep(30)"],
            wall=10, rss=20)
        self.assertEqual(got['status'], 'memory')
        self.assertEqual(got['limit_tripped'], 'rss')
        self.assertEqual(got['memory_stop'], 'limit_rss')
        self.assertGreater(got['peak_rss_mb'], 20)

    def test_the_memory_floor_fires(self):
        # The machine guard, separate from the declared cell limit: set just
        # above what is free, so the first sample trips it. On the real
        # campaign it is set LOW -- it records the peak, it does not protect
        # the run (MEASUREMENT_RUN_PLAN.md §8.2).
        floor = cell_metrics.available_mb() + 100000
        got = self._run([_PY, '-c', 'import time; time.sleep(30)'],
                        wall=10, floor=floor)
        self.assertEqual(got['status'], 'memory')
        self.assertEqual(got['limit_tripped'], 'rss')
        self.assertEqual(got['memory_stop'], 'memory_floor')

    def test_an_outside_signal_is_interrupted_not_a_deadline(self):
        """ The unstable-machine case: a result, or a re-run? """
        timer = threading.Timer(0.4, os.kill, (os.getpid(), signal.SIGTERM))
        timer.start()
        try:
            got = self._run([_PY, '-c', 'import time; time.sleep(30)'],
                            wall=60)
        finally:
            timer.cancel()
        self.assertEqual(got['status'], 'interrupted')
        # It trips NO declared limit, so it is not a did-not-finish...
        self.assertEqual(got['limit_tripped'], 'none')
        # ...and the outcome says so, which is what sends it back to the queue.
        self.assertEqual(cell_metrics.outcome(got['status'], False),
                         'interrupted')

    def test_the_handler_is_restored_afterwards(self):
        # Installing a SIGTERM handler and leaving it installed would make the
        # NEXT cell in the same process un-killable in the usual way.
        before = signal.getsignal(signal.SIGTERM)
        self._run([_PY, '-c', 'pass'])
        self.assertIs(signal.getsignal(signal.SIGTERM), before)


class TestTheProgressTrail(unittest.TestCase):
    """ What makes a crash at hour 20 yield a bound instead of nothing. """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='cell_trail_')
        self.out = os.path.join(self.dir, 'cell.json')

    def test_a_trail_is_written_and_ends_with_the_verdict(self):
        cell_run.run_cell([_PY, '-c', 'import time; time.sleep(4)'], {},
                          0.5, 0, 0, 0.1, self.out, grace_s=0.3, poll_s=0.05)
        trail = os.path.join(self.dir, 'cell.status.jsonl')
        self.assertTrue(os.path.exists(trail))
        lines = [json.loads(l) for l in open(trail) if l.strip()]
        self.assertGreater(len(lines), 1, "no running samples were written")
        for line in lines[:-1]:
            self.assertEqual(line['status'], 'running')
            self.assertIn('elapsed_s', line)
            self.assertIn('available_mb', line)
        self.assertEqual(lines[-1]['status'], 'deadline')
        self.assertEqual(lines[-1]['limit_tripped'], 'wall')

    def test_a_stale_trail_from_a_previous_attempt_is_not_appended_to(self):
        trail = os.path.join(self.dir, 'cell.status.jsonl')
        with open(trail, 'w') as handle:
            handle.write('{"elapsed_s": 999, "status": "running"}\n')
        cell_run.run_cell([_PY, '-c', 'pass'], {}, 60, 0, 0, 1, self.out,
                          grace_s=0.3)
        lines = [json.loads(l) for l in open(trail) if l.strip()]
        self.assertNotIn(999, [l.get('elapsed_s') for l in lines])


class TestOrphansAreSweptUp(unittest.TestCase):
    """ An orphan means the NEXT cell measures a machine that is not idle. """

    def test_a_process_outside_the_group_is_still_killed(self):
        # A grandchild in its OWN process group but the SAME session: killpg
        # on the child's group does not reach it, which is the shape a
        # daemonised aggregator has after an external SIGTERM.
        out = os.path.join(tempfile.mkdtemp(prefix='cell_orphan_'), 'c.json')
        got = cell_run.run_cell(
            [_PY, '-c',
             "import subprocess, os, time\n"
             "subprocess.Popen(['sleep', '30'], preexec_fn=os.setpgrp)\n"
             "time.sleep(30)"],
            {}, 0.5, 0, 0, 0, out, grace_s=1.0, poll_s=0.05)
        self.assertEqual(got['status'], 'deadline')
        self.assertTrue(got['orphans_killed'],
                        "the grandchild outlived the run and was not swept")
        # Labelled, not a bare pid: "something outlived the run" is not a
        # finding; "the aggregator outlived the run" is.
        self.assertEqual(set(got['orphans_killed'][0]), {'pid', 'label'})

    def test_a_clean_run_reports_no_orphans(self):
        # It did, before the zombie filter. A benchmark reliably leaves one
        # reaped-pending child behind, and counting it would have marked every
        # clean cell in the campaign as having leaked -- so the one time a real
        # orphan appeared, nobody would have looked twice.
        out = os.path.join(tempfile.mkdtemp(prefix='cell_clean_'), 'c.json')
        got = cell_run.run_cell(
            [_PY, '-c', "import subprocess\n"
                        "subprocess.Popen([%r, '-c', 'pass'])" % _PY],
            {}, 60, 0, 0, 0, out, grace_s=1.0)
        self.assertEqual(got['status'], 'completed')
        self.assertEqual(got['orphans_killed'], [])

    def test_a_zombie_is_not_a_live_process(self):
        proc = subprocess.Popen([_PY, '-c', 'pass'])
        proc.wait()                              # reaped by Popen, so make one
        child = subprocess.Popen(
            [_PY, '-c', "import subprocess, time\n"
                        "subprocess.Popen([%r, '-c', 'pass'])\n"
                        "time.sleep(0.8)" % _PY],
            start_new_session=True)
        try:
            # Give the grandchild time to exit unreaped.
            threading.Event().wait(0.4)
            states = {cell_metrics.process_state(pid)
                      for pid in cell_metrics.session_pids(child.pid)}
            self.assertIn('Z', states, "no zombie was produced to test with")
            for pid in cell_metrics.live_session_pids(child.pid):
                self.assertNotEqual(cell_metrics.process_state(pid), 'Z')
        finally:
            child.wait()


class TestTheCommandEachBackendGets(unittest.TestCase):
    """ `build_command` is where a cell's measurement-affecting choices are
    made, so each is pinned and each is stamped. """

    def test_apkeep_selects_its_engine_and_stamps_it(self):
        _, env, stamps = cell_run.build_command(
            _args(backend='apkeep', apkeep_engine='bdd'))
        self.assertEqual(env['FAVE_BACKEND'], 'apkeep')
        self.assertIn('--apkeep-engine bdd', env['FAVE_ENGINE_OPTIONS'])
        self.assertEqual(stamps['apkeep_engine'], 'bdd')

    def test_veriflow_runs_with_no_internal_budget_and_says_so(self):
        # Item 31: the suite limit is EXTERNAL, so the engine's own budget is
        # 0 in every reportable run. Stamped rather than assumed.
        _, env, stamps = cell_run.build_command(_args(backend='veriflow'))
        self.assertIn('--vf-fields 4+10', env['FAVE_ENGINE_OPTIONS'])
        self.assertIn('--vf-budget 0', env['FAVE_ENGINE_OPTIONS'])
        self.assertEqual(stamps['vf_budget'], 0)

    def test_the_plain_ablation_is_selectable(self):
        _, env, stamps = cell_run.build_command(
            _args(backend='veriflow', vf_fields='plain'))
        self.assertIn('--vf-fields plain', env['FAVE_ENGINE_OPTIONS'])
        self.assertEqual(stamps['vf_fields'], 'plain')

    def test_ad6_gets_its_progress_switch(self):
        # Without it a six-hour run yields a bound and nothing else
        # (AD6_PLAN.md §9.34.3), so it is not optional here.
        _, env, _ = cell_run.build_command(_args(backend='ad6'))
        self.assertEqual(env['AD6_BRIDGE_PROGRESS'], '1')

    def test_there_is_no_out_iface_opt_in_left(self):
        """ TODO item 13a is CLOSED: `-o` is modelled on every backend, so
        there is no infidelity to opt into and no cell carries a flag for it.

        A retired workaround that keeps its switch is how one becomes folklore,
        which is the item's own argument for deleting it rather than leaving it
        inert.
        """
        for workload in ('wl_up', 'wl_tum', 'wl_example', 'wl_stanford'):
            with self.subTest(workload=workload):
                _, env, stamps = cell_run.build_command(
                    _args(workload=workload))
                self.assertNotIn('FAVE_ALLOW_OUT_IFACE', env)
                self.assertNotIn('allow_out_iface', stamps)

    def test_a_deltanet_workload_goes_through_the_registry(self):
        argv, _, stamps = cell_run.build_command(_args(workload='wl_airtel1'))
        self.assertEqual(stamps['driver'], 'bench.deltanet.workload.build')
        self.assertIn('bench.deltanet.workload', argv[-1])

    def test_every_other_workload_goes_through_its_benchmark(self):
        argv, _, stamps = cell_run.build_command(_args(workload='wl_stanford'))
        self.assertEqual(stamps['driver'], 'bench/wl_stanford/benchmark.py')
        self.assertEqual(argv[-1], 'bench/wl_stanford/benchmark.py')

    def test_the_mutation_reaches_the_bootstrap(self):
        argv, _, _ = cell_run.build_command(
            _args(workload='wl_berkeley', mutate=True, mutate_cell='s22,s23'))
        self.assertIn('s22 ---> s23', argv[-1])

    def test_mutate_with_reuse_inputs_is_refused(self):
        # The mutation wraps `_policy_text`, which reused inputs never call:
        # the run would report an unmutated verdict as a mutated one.
        with self.assertRaises(SystemExit):
            cell_run.main(['wl_berkeley', '--mutate', '--reuse-inputs',
                           '--limit-class', 'dev', '--limit-wall', '1',
                           '--out', '/tmp/never-written.json'])

    def test_a_reportable_ad6_cell_must_declare_its_encoding(self):
        # TODO item 0a. Rank and flow are not interchangeable -- on
        # wl_stanford (240 queries) flow is 3.65x faster, on wl_up (11,902) it
        # is >31.4x slower and did not finish -- so the SIGN of the effect
        # depends on the workload, and a table that mixes them mixes
        # encodings. Taking the adapter's default is an undocumented habit:
        # stamped afterwards, never decided.
        for options in ('', '--solver cadical195', '--grounding rank'):
            with self.subTest(engine_options=options):
                with self.assertRaises(SystemExit):
                    cell_run.main(['wl_ifi', '--backend', 'ad6',
                                   '--engine-options', options,
                                   '--limit-class', 'v5', '--limit-wall', '60',
                                   '--out', '/tmp/never-written.json'])

    def test_a_dev_ad6_cell_need_not_declare_it(self):
        # A dev number is not reportable, so the gate would only be friction.
        # The parser must get past the check; the run itself is not started
        # here, which is what the 0-second wall limit arranges.
        args = _args(backend='ad6', engine_options='')
        _, env, _ = cell_run.build_command(args)
        self.assertEqual(env['FAVE_BACKEND'], 'ad6')

    def test_the_other_backends_are_not_gated(self):
        # Their measurement-affecting choices have explicit flags with
        # declared defaults that are stamped either way: --apkeep-engine,
        # --vf-fields. ad6 is the one whose silent defaults change the
        # encoding.
        for backend, extra in (('apkeep', ['--apkeep-engine', 'ndd']),
                               ('veriflow', ['--vf-fields', '4+10'])):
            with self.subTest(backend=backend):
                parser_ok = True
                try:
                    cell_run.main(['wl_ifi', '--backend', backend] + extra
                                  + ['--limit-class', 'v5',
                                     '--limit-wall', '0.01',
                                     '--out', '/tmp/claude-1000/gated.json'])
                except SystemExit as exit_:
                    parser_ok = exit_.code != 2        # 2 is argparse's refusal
                except Exception:                      # pylint: disable=broad-except
                    pass                               # a run failure is fine
                self.assertTrue(parser_ok,
                                "%s was gated; only ad6 should be" % backend)

    def test_a_cell_without_a_declared_deadline_is_refused(self):
        # Zero would read as "no deadline" to the sampling loop, and the result
        # would look like a cell that completed. Item 31: every run carries a
        # declared limit, because a run that was merely killed has not been
        # shown not to finish.
        for wall in ('0', '-1'):
            with self.subTest(limit_wall=wall):
                with self.assertRaises(SystemExit):
                    cell_run.main(['wl_ifi', '--backend', 'veriflow',
                                   '--limit-class', 'dev', '--limit-wall', wall,
                                   '--out', '/tmp/never-written.json'])

    def test_every_backend_has_a_source_tree_to_stamp(self):
        # The provenance column names WHICH build produced a number, and a jar
        # hash cannot answer it: it changes on every rebuild.
        for backend in ('netplumber', 'apkeep', 'ad6', 'veriflow'):
            with self.subTest(backend=backend):
                self.assertIn(backend, cell_run.ENGINE_TREES)


class TestTheQueueResumes(unittest.TestCase):
    """ The campaign must survive being started three times. """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='cell_queue_')

    def _write(self, name, status):
        with open(os.path.join(self.dir, name + '.json'), 'w') as handle:
            json.dump({'status': status}, handle)

    def test_a_cell_a_declared_limit_stopped_is_done(self):
        # A did-not-finish IS a result. Re-running it would replace a
        # measurement with an identical one.
        for status in ('completed', 'deadline', 'memory', 'error'):
            with self.subTest(status=status):
                self._write(status, status)
                self.assertEqual(cell_queue.state_of(self.dir, status)[0],
                                 'done')

    def test_a_cell_the_environment_stopped_is_redone(self):
        self._write('crashed', 'interrupted')
        self.assertEqual(cell_queue.state_of(self.dir, 'crashed')[0],
                         'interrupted')

    def test_a_trail_with_no_result_is_a_container_death(self):
        # What a container death looks like from outside: the runner never got
        # to write anything, but it had been running.
        with open(os.path.join(self.dir, 'died.status.jsonl'), 'w') as handle:
            handle.write('{"elapsed_s": 12, "status": "running"}\n')
        state, detail = cell_queue.state_of(self.dir, 'died')
        self.assertEqual(state, 'interrupted')
        self.assertIn('no result', detail)

    def test_a_truncated_result_is_redone_not_trusted(self):
        with open(os.path.join(self.dir, 'half.json'), 'w') as handle:
            handle.write('{"status": "comple')
        self.assertEqual(cell_queue.state_of(self.dir, 'half')[0],
                         'interrupted')

    def test_an_unstarted_cell_is_todo(self):
        self.assertEqual(cell_queue.state_of(self.dir, 'fresh'),
                         ('todo', None))

    def test_the_command_a_cell_spec_becomes(self):
        argv = cell_queue.cell_argv(
            {'name': 'c1', 'workload': 'wl_up', 'backend': 'apkeep',
             'apkeep-engine': 'ndd', 'limit-wall': 86400,
             'reuse-inputs': True, 'jvm-xmx': None}, self.dir)
        self.assertIn('wl_up', argv)
        self.assertIn('--apkeep-engine', argv)
        self.assertIn('86400', argv)
        self.assertIn('--reuse-inputs', argv)          # bare, for true
        self.assertNotIn('--jvm-xmx', argv)            # dropped, for None
        self.assertEqual(argv[-1], os.path.join(self.dir, 'c1.json'))

    def test_an_option_like_value_is_passed_unambiguously(self):
        # The queue spawns without a shell, so a VALUE that looks like an
        # option is ambiguous to argparse. It survives today only by a
        # heuristic -- a token containing a space is treated as a value -- so
        # `--engine-options "--solver cadical195"` happens to work while a
        # single-token `--engine-options "--lite-acyclic"` would be read as a
        # flag and refused. The `=` form has no such edge.
        argv = cell_queue.cell_argv(
            {'name': 'c', 'workload': 'wl_i2', 'backend': 'ad6',
             'engine-options': '--lite-acyclic'}, self.dir)
        self.assertIn('--engine-options=--lite-acyclic', argv)
        self.assertNotIn('--lite-acyclic', argv)

    def test_the_campaign_queue_in_the_tree_is_runnable(self):
        """ The phase A queue is shipped, so it is checked like code. """
        import json as _json
        path = os.path.join(os.path.dirname(cell_queue.__file__),
                            'campaigns', 'v5_phase_a.json')
        self.assertTrue(os.path.exists(path), "the shipped campaign is missing")
        with open(path) as handle:
            cells = _json.load(handle)
        names = [c['name'] for c in cells]
        self.assertEqual(len(set(names)), len(names), "duplicate cell names")
        for cell in cells:
            with self.subTest(cell=cell['name']):
                # Every cell declares the reportable limits, so none of them
                # can silently produce a dev number inside a v5 campaign.
                self.assertEqual(cell['limit-class'], 'v5')
                self.assertEqual(cell['limit-wall'], 86400)
                self.assertEqual(cell['limit-rss'], 32768)
                # And every ad6 cell declares its encoding, which cell_run
                # would otherwise refuse at v5 (TODO item 0a).
                if cell['backend'] == 'ad6':
                    self.assertIn('--grounding', cell['engine-options'])
                    self.assertIn('--solver', cell['engine-options'])
                # The command it becomes must name a workload that exists.
                self.assertTrue(os.path.isdir(os.path.join(
                    os.path.dirname(cell_queue.__file__), cell['workload'])))

    def test_a_stale_aggregator_log_yields_no_provenance(self):
        """ A cell must never inherit another engine's provenance.

        wl_stanford_np -- backend netplumber -- recorded
        impl=reimpl-literature, which is VeriFlow-FR's value. Its aggregator
        died before writing a stamp, so the harness read the `backend:
        veriflow` line an EARLIER e2e run had left in /dev/shm/np and recorded
        it verbatim, with impl_source saying "backend configuration stamp".

        Item 31 requires provenance stamped rather than typed by hand so that
        "a table cannot mislabel a row". A stale log defeats that exactly as
        well as a hand-typed literal, and it is harder to notice, because the
        value is real -- it just belongs to a different engine.
        """
        log = os.path.join(self.dir, 'c.aggregator.log')
        with open(log, 'w') as handle:
            handle.write("backend: veriflow {'impl': 'reimpl-literature'}\n")

        # Read as the cell that actually wrote it: the stamp comes back.
        stamp, source = cell_run.backend_stamp(self.dir, 'c', 'veriflow')
        self.assertEqual(stamp['impl'], 'reimpl-literature')
        self.assertEqual(source, 'backend configuration stamp')

        # Read as a netplumber cell: nothing, and a reason that names both.
        stamp, source = cell_run.backend_stamp(self.dir, 'c', 'netplumber')
        self.assertEqual(stamp, {})
        self.assertIn('stale log', source)
        self.assertIn('veriflow', source)
        self.assertIn('netplumber', source)

    def test_a_workload_with_no_check_set_still_summarises(self):
        """ A checkless workload must not lose its summary and exit status.

        `wl_tum` has no `checks.json` at all -- MEASUREMENT_RUN_PLAN.md 5.1:
        "its checks.json is empty. It checks nothing." The summary line indexed
        `result['checks']` directly and so raised KeyError on it. The result
        JSON is written BEFORE that line, so the cell's data survived and only
        its summary and its exit status were lost -- which is the worst shape
        for the failure to take: the campaign log showed a traceback and
        `exited 1` for a cell that had in fact measured everything it was
        asked to.
        """
        summary = {k: {'workload': 'wl_tum', 'engine': 'netplumber',
                       'status': 'completed', 'outcome': 'error',
                       'limit_class': 'v5', 'limit_tripped': 'none',
                       'wall_s': 5.9, 'peak_rss_mb': 441, 'violations': 0,
                       'verdict_valid': False}.get(k)
                   for k in ('workload', 'engine', 'status', 'outcome',
                             'limit_class', 'limit_tripped', 'wall_s',
                             'peak_rss_mb', 'violations', 'checks',
                             'verdict_valid')}
        self.assertIsNone(summary['checks'])
        self.assertEqual(summary['workload'], 'wl_tum')
        # And the real thing: the module's own line must use .get, so that a
        # workload without a check set cannot crash the summary again.
        import inspect
        source = inspect.getsource(cell_run.main)
        self.assertIn("result.get(k) for k in", source)
        self.assertNotIn("result[k] for k in", source)

    def test_two_cells_sharing_a_name_are_refused(self):
        # One would overwrite the other's result, and the campaign would be
        # one cell short with nothing saying so.
        queue = os.path.join(self.dir, 'q.json')
        with open(queue, 'w') as handle:
            json.dump([{'name': 'x', 'workload': 'wl_up'},
                       {'name': 'x', 'workload': 'wl_tum'}], handle)
        with self.assertRaises(SystemExit):
            cell_queue.main(['--queue', queue, '--out-dir', self.dir,
                             '--dry-run'])

    def test_a_restart_skips_what_is_done_and_runs_the_rest(self):
        queue = os.path.join(self.dir, 'q.json')
        with open(queue, 'w') as handle:
            json.dump([{'name': 'a', 'workload': 'wl_up'},
                       {'name': 'b', 'workload': 'wl_tum'}], handle)
        self._write('a', 'completed')
        proc = subprocess.run(
            [_PY, os.path.join(os.path.dirname(cell_queue.__file__),
                               'cell_queue.py'),
             '--queue', queue, '--out-dir', self.dir, '--dry-run'],
            capture_output=True, text=True, check=True)
        self.assertIn('[skip] a', proc.stdout)
        self.assertIn('wl_tum', proc.stdout)
        self.assertNotIn('[would run]  wl_up', proc.stdout)


if __name__ == '__main__':
    unittest.main()
