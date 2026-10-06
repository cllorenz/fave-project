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

""" ONE CELL of the comparison: one engine, one workload, under a declared limit.

TODO item 31's unchecked box -- *"Build the harness mechanism and the stamps"* --
and `MEASUREMENT_RUN_PLAN.md` §3. It generalises
`bench/deltanet/eval/engine_run.py`, which measured all of this already but only
for the Delta-net family, to every workload and all four backends, and adds the
five stamps item 31 names. None of them existed anywhere in the tree on
2026-10-02: no result file said under which limit it was produced.

WHAT A CELL RECORDS, and why each part is not optional:

* **The declared limits**, `limit_wall_s` and `limit_rss_mb`, with
  `limit_class` (`v5` reportable, `dev` never) and the `machine`. Item 31 fixes
  the reportable limit at 24 h and 32 GB and requires the machine description
  stamped beside it; `CLOUD_BENCH_PLAN.md` §2.15 had to put its machine in
  prose because no result carried one.
* **`limit_tripped`** -- `wall`, `rss` or `none`. Enforcement is EXTERNAL and
  identical for every engine: a wall-clock timeout plus a peak-memory monitor,
  never `RLIMIT_AS`, which misfires on the JVM.
* **`outcome`** -- what the cell says about the ENGINE, which is a different
  question from what ended the run. A run the environment killed is
  `interrupted` and is **re-run**; only a run a DECLARED limit killed is a
  `did_not_finish`. Recording the first as the second manufactures a finding.
* **A progress trail**, `<out>.status.jsonl`, one line every `--status-every`
  seconds. On a machine that is a container in a VM on a shared server this is
  what makes a crash at hour 20 yield a lower bound instead of nothing, and it
  is how the queue tells an interrupted cell from one never started.
* **Provenance**, `impl`, stamped BY THE BACKEND and never typed by hand, so a
  table cannot mislabel a row.

RUNNING OUT OF MEMORY IS A FAITHFUL RESULT (owner, 2026-10-02). An OOM is the
cell's outcome, recorded with its peak RSS, and is not retried smaller. That is
why `--memory-floor` should be set LOW rather than conservatively: the floor is
here to RECORD the peak, not to protect the run. The harness kills at the floor
and writes the peak RSS it measured; the kernel's OOM killer writes a dmesg line
and may take a process other than the one under test.

Usage (from fave/, venv active, PYTHONPATH=.):

    python3 bench/cell_run.py wl_stanford --backend apkeep --apkeep-engine ndd \\
        --limit-class v5 --limit-wall 86400 --limit-rss 32768 \\
        --out results/stanford_ndd.json
"""

import argparse
import ast
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

from bench import cell_metrics                           # noqa: E402

AGGREGATOR_LOG = '/dev/shm/np/aggregator.log'
REPORT = 'report.md'

_TASK = re.compile(r'completed task check_compliance in ([0-9.e+-]+) seconds')
_REPORT = re.compile(r'completed task report in ([0-9.e+-]+) seconds')
_LOAD = re.compile(r'completed task switch_command in ([0-9.e+-]+) seconds')
_DONE = re.compile(r'completed task ([a-z_]+)')

JARS = {
    'apkeep_jar': '../apkeep/target/apkeep-1.0.0.jar',
    'ndd_jar': '../ndd/target/ndd-1.0.1-jar-with-dependencies.jar',
}

#: Engine source trees, hashed into the cell so that item 31's provenance
#: column names WHICH build produced a number. A jar hash alone cannot: it
#: changes on every rebuild, so it distinguishes builds but not code. The
#: commit is what `MEASUREMENT_RUN_PLAN.md` §5.0's staleness test (S1) keys on.
ENGINE_TREES = {
    'netplumber': '../net_plumber',
    'apkeep': '../apkeep',
    'ad6': '../ad6',
    'veriflow': 'veriflow',
}

#: TODO item 13a: `-o` in a FORWARD rule is inert, because FaVe's packet filter
#: chains BEFORE it routes, so `out_port` is still unset when the rule is
#: evaluated. Without the opt-in the generator refuses the ruleset outright.
#:
#: The bootstrap for the Delta-net family, which is built by a registry rather
#: than by a `benchmark.py` of its own. Copied from `engine_run.py`, whose
#: results must stay re-derivable from it, so the two must not drift.
_DELTANET_BOOTSTRAP = """
import logging, sys
import bench.deltanet.workload as workload
logging.basicConfig(level=logging.INFO)
run = workload.build(%(name)r, **%(options)r)
if %(mutate)r:
    _emit = run._policy_text
    def _mutated(*args):
        head, sep, tail = _emit(*args).rpartition('\\nend')
        if not sep:
            raise SystemExit('no policy block to mutate')
        return head + '\\n    ' + %(rule)r + sep + tail
    run._policy_text = _mutated
run.run()
"""


def deltanet_workloads():
    """ The Delta-net family, from its registry rather than a second list. """
    try:
        # Guarded and local on purpose: a checkout without the Delta-net
        # registry must still run every other workload's cell.
        from bench.deltanet.registry import (        # pylint: disable=import-outside-toplevel
            WORKLOADS, DERIVED)
    except ImportError:                         # pragma: no cover
        return ()
    return tuple(WORKLOADS) + tuple(DERIVED)


def engine_commit(tree):
    """ The commit that last touched an engine's source -- the staleness test
    of `MEASUREMENT_RUN_PLAN.md` §5.0 (S1), which a jar hash cannot answer. """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(here, '..', tree))
    if not os.path.isdir(path):
        return None
    proc = subprocess.run(['git', 'log', '-1', '--format=%H %ad', '--date=short',
                           '--', path], capture_output=True, text=True,
                          check=False, cwd=path)
    return proc.stdout.strip() or None


def build_command(args):
    """ The child process, its environment, and the choices that shaped them.

    Returns `(argv, env_overrides, stamps)`. Separated from `run_cell` so that
    the runner can be tested against a trivial command -- a stopping rule that
    has never fired is not a stopping rule, and firing them through a real
    benchmark would make the test a backend test.
    """
    stamps = {}
    # PYTHON is not a convenience: `scripts/start_aggr.sh` defaults to a bare
    # `python3` (`PYTHON="${PYTHON:-python3}"`), so without it the aggregator
    # starts on the SYSTEM interpreter while the benchmark runs on the venv's,
    # and dies with `No module named 'filelock'` -- which surfaces four frames
    # later as "could not connect to fave", naming nothing. `test.sh` exports
    # it for the same reason. Pinning it to `sys.executable` also gives the
    # cell the property it should have anyway: ONE interpreter throughout.
    env = {'PYTHONPATH': '.', 'FAVE_BACKEND': args.backend,
           'PYTHON': sys.executable}

    options = ''
    if args.backend == 'apkeep':
        options = '--apkeep-engine %s' % args.apkeep_engine
        stamps['apkeep_engine'] = args.apkeep_engine
    elif args.backend == 'veriflow':
        # `4+10` is VeriFlow-FR's headline per D6; `plain` is the declared
        # ablation, which does not finish on wl_up or wl_tum by design.
        options = '--vf-fields %s' % args.vf_fields
        stamps['vf_fields'] = args.vf_fields
        # The suite limit is EXTERNAL (item 31), so the engine's own budget is
        # off in every reportable run. Stamped so that is visible, not assumed.
        options += ' --vf-budget 0'
        stamps['vf_budget'] = 0
    if args.engine_options:
        options = (options + ' ' + args.engine_options).strip()
    env['FAVE_ENGINE_OPTIONS'] = options
    stamps['engine_options'] = options


    if args.jvm_xmx:
        env['FAVE_JVM_XMX'] = args.jvm_xmx

    if args.backend == 'ad6':
        # AD6_PLAN.md §9.34.3: without this a six-hour run yields a bound and
        # nothing else -- not even which query it reached, which is what would
        # have turned the bound into a per-query rate. Required for anything
        # over an hour, so it is simply always on here.
        env['AD6_BRIDGE_PROGRESS'] = '1'

    if args.workload in deltanet_workloads():
        options_kw = {}
        if args.keep_every is not None:
            options_kw['keep_every'] = args.keep_every
        if args.reuse_inputs:
            options_kw['reuse_inputs'] = True
        cell = args.mutate_cell.split(',')
        code = _DELTANET_BOOTSTRAP % {
            'name': args.workload, 'options': options_kw,
            'mutate': args.mutate, 'rule': '%s ---> %s' % tuple(cell)}
        argv = [sys.executable, '-c', code]
        stamps['driver'] = 'bench.deltanet.workload.build'
    else:
        argv = [sys.executable, 'bench/%s/benchmark.py' % args.workload]
        stamps['driver'] = 'bench/%s/benchmark.py' % args.workload

    return argv, env, stamps


def _progress(session, started, peak_rss, aggregator_log, ad6_progress):
    """ One line of the trail: enough to compute a rate after a crash.

    Engine-agnostic -- the aggregator's own completed-task counts and the log's
    size, which move for every backend -- plus whatever the engine volunteers.
    """
    line = {
        'elapsed_s': round(time.time() - started, 1),
        'peak_rss_mb': peak_rss,
        'rss_by_process_mb': cell_metrics.session_rss_mb(session),
        'available_mb': cell_metrics.available_mb(),
        'status': 'running',
    }
    if os.path.exists(aggregator_log):
        try:
            with open(aggregator_log) as handle:
                text = handle.read()
            line['aggregator_log_bytes'] = len(text)
            tasks = {}
            for name in _DONE.findall(text):
                tasks[name] = tasks.get(name, 0) + 1
            line['tasks_completed'] = tasks
        except OSError:
            pass
    if ad6_progress and os.path.exists(ad6_progress):
        try:
            with open(ad6_progress) as handle:
                tail = handle.readlines()
            if tail:
                line['ad6_progress'] = tail[-1].strip()[:200]
        except OSError:
            pass
    return line


def run_cell(argv, env_overrides, limit_wall_s, limit_rss_mb, memory_floor_mb,
             status_every_s, out, ad6_progress=None, grace_s=3.0,
             poll_s=1.0, _clock=time.time):
    """ Run one child under the two declared stopping rules, and measure it.

    The testable core: it takes a COMMAND, not a workload, so every stopping
    rule can be made to fire against `sleep` in a unit test.

    `poll_s` is how often the run is sampled, and so the GRANULARITY of both
    stopping rules: a cell is killed up to `poll_s` after it crosses a limit,
    and `peak_rss_mb` is the largest value SEEN, not the largest reached. One
    second over a 24 h cell is the right trade and is what the campaign uses;
    the unit tests drop it so that sub-second limits can be made to fire
    without the tier paying a second per rule.
    """
    out_dir = os.path.dirname(os.path.abspath(out)) or '.'
    stem = os.path.splitext(os.path.basename(out))[0]
    trail_path = os.path.join(out_dir, stem + '.status.jsonl')
    for stale in (trail_path,):
        if os.path.exists(stale):
            os.remove(stale)

    env = dict(os.environ, **env_overrides)
    interrupted = {'hit': False}

    def _on_signal(_signum, _frame):
        # The unstable-machine case made explicit: a SIGTERM from outside is
        # NOT a stopping rule, and the cell it ends is re-run rather than
        # reported. Without this the run would simply die and leave a trail
        # whose last line says `running`, which the queue would have to
        # interpret; here it says so itself.
        interrupted['hit'] = True

    previous = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, _on_signal)

    started = _clock()
    peak_rss = 0
    peak_by_process = {}
    swap_by_process = {}
    swap_at_start = peak_swap = cell_metrics.swap_used_mb()
    traffic_at_start = cell_metrics.swap_traffic()
    least_available = cell_metrics.available_mb()
    status = None
    memory_stop = None
    rc = None
    last_trail = 0.0

    try:
        with open(os.path.join(out_dir, stem + '.stdout'), 'w') as log:
            proc = subprocess.Popen(argv, env=env, stdout=log,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True)
            while status is None:
                try:
                    rc = proc.wait(timeout=poll_s)
                    status = 'completed' if rc == 0 else 'error'
                    break
                except subprocess.TimeoutExpired:
                    pass
                sampled = cell_metrics.session_rss_mb(proc.pid)
                total = sum(sampled.values())
                peak_rss = max(peak_rss, total)
                for name, mb in sampled.items():
                    peak_by_process[name] = max(peak_by_process.get(name, 0), mb)
                for name, mb in cell_metrics.session_rss_mb(
                        proc.pid, 'VmSwap:').items():
                    swap_by_process[name] = max(swap_by_process.get(name, 0), mb)
                peak_swap = max(peak_swap, cell_metrics.swap_used_mb())
                least_available = min(least_available,
                                      cell_metrics.available_mb())

                now = _clock()
                if status_every_s and now - last_trail >= status_every_s:
                    last_trail = now
                    with open(trail_path, 'a') as trail:
                        trail.write(json.dumps(_progress(
                            proc.pid, started, peak_rss, AGGREGATOR_LOG,
                            ad6_progress)) + '\n')

                if interrupted['hit']:
                    status = 'interrupted'
                elif memory_floor_mb and least_available < memory_floor_mb:
                    status, memory_stop = 'memory', 'memory_floor'
                elif limit_rss_mb and total > limit_rss_mb:
                    status, memory_stop = 'memory', 'limit_rss'
                elif limit_wall_s and now - started > limit_wall_s:
                    status = 'deadline'

                if status is not None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    rc = None
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    wall = _clock() - started

    # An external SIGTERM bypasses `run()`'s `finally`, so `_teardown` never
    # runs and the aggregator is orphaned; the pidfile fallback does not cover
    # a backend that starts no net_plumber. An orphan means the NEXT cell
    # measures a machine that is not idle, which is a silent corruption of
    # every figure after it.
    # A short grace period first: on a CLEAN exit `_teardown` is still winding
    # the aggregator down, and killing it mid-shutdown would turn a tidy run
    # into a reported orphan. Anything still alive after it is a real one.
    deadline = _clock() + grace_s
    while _clock() < deadline and cell_metrics.live_session_pids(proc.pid):
        time.sleep(0.2)
    orphans = []
    for pid in cell_metrics.live_session_pids(proc.pid):
        if pid == os.getpid():
            continue
        try:
            # Labelled, not a bare pid: "something outlived the run" is not a
            # finding, "the aggregator outlived the run" is.
            name = cell_metrics.label(pid)
        except OSError:
            name = 'gone'
        try:
            os.kill(pid, signal.SIGKILL)
            orphans.append({'pid': pid, 'label': name})
        except OSError:
            pass

    tripped = {'deadline': 'wall', 'memory': 'rss'}.get(status, 'none')
    with open(trail_path, 'a') as trail:
        trail.write(json.dumps({
            'elapsed_s': round(wall, 1), 'peak_rss_mb': peak_rss,
            'status': status, 'limit_tripped': tripped}) + '\n')

    return {
        'status': status, 'exit': rc, 'wall_s': round(wall, 3),
        'limit_tripped': tripped,
        'memory_stop': memory_stop,
        'peak_rss_mb': peak_rss,
        'peak_rss_by_process_mb': peak_by_process,
        'least_available_mb': least_available,
        'swap_used_at_start_mb': swap_at_start,
        'peak_swap_used_mb': peak_swap,
        'peak_swap_by_process_mb': swap_by_process,
        'swap_pages': {name: cell_metrics.swap_traffic()[name] - count
                       for name, count in traffic_at_start.items()},
        'orphans_killed': orphans,
        'status_trail': os.path.basename(trail_path),
    }


def read_verdict(workload, out_dir, stem, gc_log):
    """ What the run produced, read the way §3's guardrails say it must be.

    A missing `report.md` is not a clean verdict, and a count believed without
    `completed task check_compliance` in the log is how a six-hour run was once
    read as "0 violations" (`AD6_PLAN.md` §9.34.3).
    """
    prefix = 'bench/%s' % workload
    found = {}

    if os.path.exists(AGGREGATOR_LOG):
        shutil.copy(AGGREGATOR_LOG,
                    os.path.join(out_dir, stem + '.aggregator.log'))
        with open(AGGREGATOR_LOG) as handle:
            text = handle.read()
        found['check_compliance_s'] = [float(t) for t in _TASK.findall(text)]
        found['report_task_s'] = [float(t) for t in _REPORT.findall(text)]
        loads = [float(t) for t in _LOAD.findall(text)]
        found['switch_command_s'] = sum(loads) if loads else None
        found['switch_commands'] = len(loads)
    else:
        found['check_compliance_s'] = []
        found['report_task_s'] = []
        found['switch_command_s'] = None

    found['gc'] = (cell_metrics.gc_summary(gc_log)
                   if os.path.exists(gc_log) else None)

    if os.path.exists(REPORT):
        with open(REPORT) as handle:
            text = handle.read()
        shutil.copy(REPORT, os.path.join(out_dir, stem + '.report.md'))
        lines = cell_metrics.violations(text)
        found['report'] = True
        found['violations'] = len(lines)
        found['violation_lines'] = lines[:10]
    else:
        found['report'] = False
        found['violations'] = None

    checks = os.path.join(prefix, 'checks.json')
    if os.path.exists(checks):
        with open(checks) as handle:
            found['checks'] = len(json.load(handle))

    # Delta-net workloads carry these; the rest do not, and an absent stamp is
    # not an error -- it is why `engine_run.py` could not be pointed at them.
    stamp_path = os.path.join(prefix, 'SOURCE.json')
    if os.path.exists(stamp_path):
        with open(stamp_path) as handle:
            stamp = json.load(handle)
        found['input_files'] = stamp.get('files')
        found['drift_from_previous'] = stamp.get('drift_from_previous')
        for key in ('census', 'keep_every', 'lpm_sensitive_cells'):
            if key in stamp:
                found[key] = stamp[key]

    # A VERDICT IS VALID WHEN THE RUN ASKED EVERY QUESTION THE WORKLOAD HAS.
    #
    # `check_compliance` alone is the wrong test, because one workload has no
    # compliance checks at all. wl_tum carries a single universal probe and no
    # `checks.json`, so `check_compliance` is never dispatched; under the old
    # condition its report -- which exists, and says what it found -- was read
    # as no verdict, and all five of its phase A cells recorded `outcome:
    # error`. That is the failure mode §3 is meant to prevent, pointed the
    # other way: not a missing check believed, but a complete run reported as
    # an engine failure. wl_tum is a throughput cell, and a throughput cell
    # that says `error` is worse than useless in a comparison table.
    #
    # So the end-of-pipeline witness has to be a task EVERY ENGINE dispatches,
    # not merely every workload. `check_anomalies` is not it: only NetPlumber
    # runs it, and using it marked all six VeriFlow-FR cells of a re-measure
    # `error` before the mistake was caught. `report` is the aggregator's OWN
    # task -- the one that writes the report.md being read here -- and appears
    # exactly once in all 51 phase A logs across all six engine
    # configurations. `check_compliance` is additionally required exactly when
    # the workload has checks to run.
    #
    # Both must appear exactly ONCE: twice means the log spans more than one
    # run and the report cannot be attributed to either.
    found['verdict_valid'] = bool(
        found['report']
        and len(found['report_task_s']) == 1
        and (len(found['check_compliance_s']) == 1
             if 'checks' in found else not found['check_compliance_s']))
    return found


_BACKEND_LINE = re.compile(r'^backend: (\S+)(?: (\{.*\}))?\s*$', re.MULTILINE)


def backend_stamp(out_dir, stem, expected_backend=None):
    """ The engine's OWN configuration stamp, read back out of the run's log.

    Item 31 is explicit that provenance is "stamped, not typed by hand: the
    value comes from the backend ... so a table cannot mislabel a row". So this
    carries no table of its own -- it parses `backend: <name> {<stamp>}`, which
    `aggregator_service` logs from `engine.configuration_stamp()`, and reports
    what is missing rather than supplying a value the backend never claimed.

    Every backend has declared one since 2026-10-02. Before that only
    VeriFlow-FR did, and a cell on any other engine came back `impl: null`.
    """
    log = os.path.join(out_dir, stem + '.aggregator.log')
    if not os.path.exists(log):
        return {}, 'no aggregator log to read a stamp from'
    with open(log) as handle:
        found = _BACKEND_LINE.search(handle.read())
    if found is None:
        return {}, 'the log carries no `backend:` line'
    # The log must be THIS cell's. A cell whose aggregator died before writing
    # its own stamp used to inherit whatever was left in /dev/shm/np by the
    # previous run: wl_stanford_np, a netplumber cell, recorded
    # impl=reimpl-literature from an earlier e2e run's veriflow line, with
    # impl_source claiming "backend configuration stamp". Item 31 wants
    # provenance stamped rather than hand-typed so that "a table cannot
    # mislabel a row", and a stale log defeats that just as thoroughly as a
    # literal would. Report nothing rather than another engine's value.
    if expected_backend is not None and found.group(1) != expected_backend:
        return {}, ('the log is %s\'s, not %s\'s -- stale log, no stamp read'
                    % (found.group(1), expected_backend))
    if not found.group(2):
        return {}, 'the backend logged no configuration stamp (item 31)'
    try:
        # A Python dict repr, logged by the aggregator. `literal_eval` and not
        # `eval`: this file is written by the run, but a measurement harness
        # that can be made to execute what it reads is not one.
        return ast.literal_eval(found.group(2)), 'backend configuration stamp'
    except (ValueError, SyntaxError):
        return {}, 'the backend stamp did not parse'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('workload')
    parser.add_argument('--backend', default='apkeep',
                        choices=('netplumber', 'apkeep', 'ad6', 'veriflow'))
    parser.add_argument('--apkeep-engine', choices=('bdd', 'ndd'),
                        default='ndd')
    parser.add_argument('--vf-fields', choices=('4+10', 'plain'),
                        default='4+10')
    parser.add_argument('--engine-options', default='',
                        help='appended to FAVE_ENGINE_OPTIONS verbatim')
    parser.add_argument('--limit-class', choices=('v5', 'dev'), required=True,
                        help='v5 is reportable; dev never is')
    parser.add_argument('--limit-wall', type=float, required=True,
                        help='seconds; item 31 fixes the reportable limit at '
                             '86400')
    parser.add_argument('--limit-rss', type=int, default=0,
                        help='MB of summed RSS; item 31 fixes the reportable '
                             'limit at 32768. 0 disables it')
    parser.add_argument('--memory-floor', type=int, default=2000,
                        help='MB of MemAvailable below which the run is '
                             'killed. Set it LOW: the floor records the peak, '
                             'it does not protect the run')
    parser.add_argument('--status-every', type=int, default=60,
                        help='seconds between progress-trail lines; 0 is off')

    parser.add_argument('--jvm-xmx', default=None)
    parser.add_argument('--keep-every', type=int, default=None)
    parser.add_argument('--reuse-inputs', action='store_true')
    parser.add_argument('--mutate', action='store_true')
    parser.add_argument('--mutate-cell', default='s1,s8')
    parser.add_argument('--expect-violations', type=int, default=None,
                        help='declare the expected verdict and the outcome '
                             'becomes correct/wrong_verdict; without it the '
                             'honest outcome is `measured`')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    if args.mutate and args.reuse_inputs:
        parser.error('--mutate regenerates the policy; it cannot --reuse-inputs')

    # `0` would read as "no deadline" to the sampling loop, which is the one
    # thing a cell may not have: item 31 requires that EVERY run carry a
    # declared limit, and "a long-running build that is killed by the operator
    # has not been shown not to finish -- it has been shown to have been
    # killed". A limit of zero is not a declaration, it is the absence of one,
    # and it would read in the result as a cell that simply completed.
    if args.limit_wall <= 0:
        parser.error('--limit-wall must be positive: a cell without a declared '
                     'stopping rule produces no reportable did-not-finish')

    # TODO item 0a, the generality-debt gate, for the one backend whose silent
    # defaults change what is being measured. ad6's grounding and solver are
    # NOT interchangeable settings of one encoding:
    #
    #   * rank is property-agnostic and lives in the shared base encoding, so
    #     one persistent session amortises it across every query; flow names
    #     THIS query's endpoints and so forces a fresh solver per query. On
    #     wl_stanford (240 queries) flow is 3.65x FASTER; on wl_up (11,902) it
    #     is >31.4x slower and did not finish at all. The SIGN of the effect
    #     depends on the query count, so "flow is Nx faster" is not a sentence
    #     that can be completed without naming the workload.
    #   * the solver likewise: §7.5 records a 21.7x that turned out to be flow
    #     at its best solver against rank at its worst.
    #
    # A table that mixes them mixes encodings. Taking whatever the adapter
    # happens to default to (minisat22, rank) is exactly the "undocumented
    # habit" item 0a is about -- it is stamped afterwards, but it was never
    # DECIDED. So a reportable ad6 cell must say both; a dev cell need not,
    # because a dev number is not reportable anyway.
    if args.limit_class == 'v5' and args.backend == 'ad6':
        missing = [flag for flag in ('--solver', '--grounding')
                   if flag not in args.engine_options]
        if missing:
            parser.error(
                "a reportable ad6 cell must declare %s in --engine-options: "
                "the grounding and the solver are not interchangeable, and a "
                "table that mixes them mixes encodings (TODO item 0a). Use "
                "--limit-class dev for an exploratory run."
                % ' and '.join(missing))

    out_dir = os.path.dirname(os.path.abspath(args.out)) or '.'
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.out))[0]
    gc_log = os.path.join(out_dir, stem + '.gc.log')
    ad6_progress = os.path.join(out_dir, stem + '.ad6_progress.log')

    for stale in (REPORT, AGGREGATOR_LOG, gc_log, ad6_progress):
        if os.path.exists(stale):
            os.remove(stale)

    argv_child, env, stamps = build_command(args)
    if args.backend == 'apkeep':
        env['FAVE_JVM_GC_LOG'] = gc_log
    if args.backend == 'ad6':
        env['AD6_BRIDGE_PROGRESS_FILE'] = ad6_progress

    measured = run_cell(
        argv_child, env, args.limit_wall, args.limit_rss, args.memory_floor,
        args.status_every, args.out,
        ad6_progress=ad6_progress if args.backend == 'ad6' else None)
    verdict = read_verdict(args.workload, out_dir, stem, gc_log)

    result = {
        'workload': args.workload,
        'backend': args.backend,
        # The APKeep engine, or the backend itself for one that has no engine
        # choice -- a NetPlumber run labelled `bdd` is how a table comes to put
        # it in the wrong row.
        'engine': (args.apkeep_engine if args.backend == 'apkeep'
                   else args.backend),
        'mutated': args.mutate,
        'mutated_cell': args.mutate_cell.split(',') if args.mutate else None,
        'jvm_xmx': env.get('FAVE_JVM_XMX'),
        'reuse_inputs': args.reuse_inputs,
        'memory_floor_mb': args.memory_floor,
        'when': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True,
                                   check=False).stdout.strip(),
        'engine_commit': engine_commit(ENGINE_TREES[args.backend]),
    }
    result.update(stamps)
    result.update(cell_metrics.limit_stamps(
        args.limit_class, args.limit_wall, args.limit_rss,
        measured['limit_tripped']))
    result.update(measured)
    result.update(verdict)
    for name, path in JARS.items():
        result[name] = cell_metrics.sha256(path)

    stamp, result['impl_source'] = backend_stamp(out_dir, stem,
                                                 args.backend)
    # The engine's own stamp, verbatim, under one key -- so a backend that
    # starts declaring something new needs no change here to have it recorded.
    result['backend_stamp'] = stamp
    result['impl'] = stamp.get('impl')
    result['upstream'] = stamp.get('upstream')
    result['expected_violations'] = args.expect_violations
    result['outcome'] = cell_metrics.outcome(
        result['status'], result['verdict_valid'], args.expect_violations,
        result['violations'])

    with open(args.out, 'w') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    # `.get`, not `[...]`: a workload need not HAVE a check set. `wl_tum`'s
    # checks.json does not exist at all (MEASUREMENT_RUN_PLAN.md 5.1: "it
    # checks nothing"), and this line used to raise KeyError on it -- AFTER the
    # result had been written, so the cell's data was complete and only its
    # summary and its exit status were lost. A null here is the honest value.
    print(json.dumps({k: result.get(k) for k in (
        'workload', 'engine', 'status', 'outcome', 'limit_class',
        'limit_tripped', 'wall_s', 'peak_rss_mb', 'violations', 'checks',
        'verdict_valid')}))
    if args.mutate:
        print("NOTE: artifacts under bench/%s are MUTATED; regenerate them "
              "before the next cell" % args.workload, file=sys.stderr)
    return 0 if result['outcome'] in ('correct', 'measured',
                                      'did_not_finish') else 1


if __name__ == '__main__':
    sys.exit(main())
