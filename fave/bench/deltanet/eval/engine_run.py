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

""" One Delta-net workload, one engine, one run -- and what the run proved.

Written for the BDD-APKeep measurement of 2026-09-29 (CLOUD_BENCH_PLAN.md
§2.13), so that its figures come from a script rather than from shell history,
which is how §2.13's own mutation check was done and why it could not be
re-derived. It drives the ordinary benchmark path -- `bench.deltanet.workload.
build(name).run()`, the aggregator selected by `FAVE_BACKEND` /
`FAVE_ENGINE_OPTIONS` exactly as `generic_benchmark.py` documents -- and then
reads what §3's guardrails say a result must be read from:

* `completed task check_compliance in X seconds` in the aggregator log -- the
  "compliance time" §2.13 tabulates, and the proof the check ran at all;
* `report.md`, whose violation lines are COUNTED, not eyeballed;
* `checks.json`, for the denominator;
* the workload's input hashes (`SOURCE.json`), recorded per run so that
  "every engine got the same inputs" is checked ACROSS runs, and the stamp's
  `drift_from_previous` -- `run()`'s own comparison with the run before it,
  made before it re-stamps (since 2026-09-29; before that `check_stamp()` after
  a run compared the run with itself, §2.13).

`--mutate` adds `s1 ---> s8` to the generated FPL -- §2.6's non-vacuity check,
a cell the data plane cannot satisfy because s8 homes no prefix. `--mutate-cell
s22,s23` picks another; `wl_berkeley`'s is 22 -> 23, the one off-diagonal cell
its walk finds unreached (§2.15). It is applied in-process around the
benchmark's `_policy_text`, because `run()` regenerates the policy every time
and an edited file would be overwritten. A mutated run leaves the
workload's artifacts MUTATED; regenerate them afterwards
(`bash test/gen_deltanet_inputs.sh`), which is what `--mutate` reminds of.

A run that exceeds `--deadline` is killed and recorded as `status: deadline` --
the declared stopping rule (§3), so a slow engine is never mistaken for a
finished one or a failed one. The second stopping rule is memory (added for
`wl_berkeley`, §2.15, whose model alone takes 12 GB of a 19 GB machine): the
run's processes are sampled every second, and when the machine's
`MemAvailable` falls below `--memory-floor` the run is killed and recorded as
`status: memory`. The peak summed RSS of the run's processes is recorded
either way, so "how much did it need" has a number even for a run that
finished.

Usage (from fave/, venv active):

    python3 bench/deltanet/eval/engine_run.py wl_airtel1 --engine bdd \\
        --deadline 2700 --out run.json [--mutate]
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

AGGREGATOR_LOG = '/dev/shm/np/aggregator.log'
REPORT = 'report.md'
_TASK = re.compile(r'completed task check_compliance in ([0-9.e+-]+) seconds')
_LOAD = re.compile(r'completed task switch_command in ([0-9.e+-]+) seconds')

_BOOTSTRAP = """
import logging, sys
import bench.deltanet.workload as workload
logging.basicConfig(level=logging.INFO)
run = workload.build(%(name)r, **%(options)r)
if %(mutate)r:
    _emit = run._policy_text
    def _mutated(*args):
        # INSIDE the policy block: a rule after its closing `end` is ignored
        # by FPL without a word, which is how the first attempt at this
        # silently mutated nothing.
        head, sep, tail = _emit(*args).rpartition('\\nend')
        if not sep:
            raise SystemExit('no policy block to mutate')
        return head + '\\n    ' + %(rule)r + sep + tail
    run._policy_text = _mutated
run.run()
"""

JARS = {
    'apkeep_jar': '../apkeep/target/apkeep-1.0.0.jar',
    'ndd_jar': '../ndd/target/ndd-1.0.1-jar-with-dependencies.jar',
}


def _sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _available_mb():
    with open('/proc/meminfo') as handle:
        for line in handle:
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) // 1024
    raise RuntimeError('no MemAvailable in /proc/meminfo')


def _label(pid):
    """ Which part of the run a process is: the `-c` bootstrap is the
    benchmark, the aggregator carries APKeep in-process (JPype), and
    `net_plumber` is NetPlumber's C++ server. """
    with open('/proc/%s/cmdline' % pid, 'rb') as handle:
        argv = handle.read().split(b'\0')
    text = b' '.join(argv).decode(errors='replace')
    for label in ('aggregator', 'net_plumber'):
        if label in text:
            return label
    if b'-c' in argv[1:2]:
        return 'benchmark'
    return os.path.basename(argv[0].decode(errors='replace')) or 'other'


def _session_rss_mb(session):
    """ `{label: summed RSS}` over every process in `session` -- the
    benchmark, the aggregator and whatever engine it started
    (`start_new_session`). """
    totals = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/%s/stat' % pid) as handle:
                fields = handle.read().rsplit(')', 1)[1].split()
            if int(fields[3]) != session:       # field 6: session id
                continue
            label = _label(pid)
            with open('/proc/%s/status' % pid) as handle:
                for line in handle:
                    if line.startswith('VmRSS:'):
                        totals[label] = (totals.get(label, 0)
                                         + int(line.split()[1]) // 1024)
        except (OSError, IndexError, ValueError):
            continue                            # exited while sampled
    return totals


def _violations(report_text):
    """ The violation lines of the Compliance Check section, counted. """
    section = report_text.split('## Compliance Check', 1)[-1]
    section = section.split('\n## ', 1)[0]
    return [line for line in section.splitlines() if line.startswith('- `')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('workload')
    parser.add_argument('--backend', default='apkeep')
    parser.add_argument('--engine', choices=('bdd', 'ndd'), default='bdd')
    parser.add_argument('--deadline', type=float, required=True,
                        help='seconds; the declared stopping rule')
    parser.add_argument('--memory-floor', type=int, default=1500,
                        help='MB of MemAvailable below which the run is '
                             'killed; the second declared stopping rule')
    parser.add_argument('--keep-every', type=int, default=None,
                        help='a derived workload at 1/k of its prefixes plus '
                             'every LPM witness (bench/deltanet/sample.py)')
    parser.add_argument('--mutate', action='store_true')
    parser.add_argument('--mutate-cell', default='s1,s8',
                        help='SOURCE,TARGET the mutation permits (default '
                             'airtel\'s s1,s8)')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    prefix = 'bench/%s' % args.workload
    for stale in (REPORT, AGGREGATOR_LOG):
        if os.path.exists(stale):
            os.remove(stale)

    env = dict(os.environ, PYTHONPATH='.', FAVE_BACKEND=args.backend,
               FAVE_ENGINE_OPTIONS=('--apkeep-engine %s' % args.engine
                                    if args.backend == 'apkeep' else ''))
    cell = args.mutate_cell.split(',')
    rule = '%s ---> %s' % tuple(cell)
    options = ({} if args.keep_every is None
               else {'keep_every': args.keep_every})
    code = _BOOTSTRAP % {'mutate': args.mutate, 'name': args.workload,
                         'rule': rule, 'options': options}
    out_dir = os.path.dirname(os.path.abspath(args.out))
    stem = os.path.splitext(os.path.basename(args.out))[0]

    started = time.time()
    with open(os.path.join(out_dir, stem + '.stdout'), 'w') as log:
        proc = subprocess.Popen([sys.executable, '-c', code], env=env,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        peak_rss = 0
        peak_by_process = {}
        least_available = _available_mb()
        status = None
        while status is None:
            try:
                rc = proc.wait(timeout=1)
                status = 'completed' if rc == 0 else 'error'
                break
            except subprocess.TimeoutExpired:
                pass
            sampled = _session_rss_mb(proc.pid)
            peak_rss = max(peak_rss, sum(sampled.values()))
            for label, mb in sampled.items():
                peak_by_process[label] = max(peak_by_process.get(label, 0), mb)
            least_available = min(least_available, _available_mb())
            if least_available < args.memory_floor:
                status = 'memory'
            elif time.time() - started > args.deadline:
                status = 'deadline'
            if status is not None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                rc = None
    wall = time.time() - started

    result = {
        'workload': args.workload, 'backend': args.backend,
        # The APKeep engine, or the backend itself for one that has no engine
        # choice -- `--engine` defaults to bdd, and a NetPlumber run labelled
        # `bdd` is how a table comes to put it in the wrong row.
        'engine': args.engine if args.backend == 'apkeep' else args.backend,
        'mutated': args.mutate,
        'mutated_cell': cell if args.mutate else None,
        'deadline_s': args.deadline, 'status': status, 'exit': rc,
        'wall_s': round(wall, 3),
        'memory_floor_mb': args.memory_floor, 'peak_rss_mb': peak_rss,
        'peak_rss_by_process_mb': peak_by_process,
        'least_available_mb': least_available,
        'when': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True,
                                   check=False).stdout.strip(),
    }
    for label, path in JARS.items():
        result[label] = _sha256(path) if os.path.exists(path) else None

    if os.path.exists(AGGREGATOR_LOG):
        shutil.copy(AGGREGATOR_LOG, os.path.join(out_dir, stem + '.aggregator.log'))
        with open(AGGREGATOR_LOG) as handle:
            log_text = handle.read()
        times = [float(t) for t in _TASK.findall(log_text)]
        result['check_compliance_s'] = times
        # Loading the rules is the other cost that scales with the model:
        # the sum over every `switch_command` task, one per device table.
        loads = [float(t) for t in _LOAD.findall(log_text)]
        result['switch_command_s'] = sum(loads)
        result['switch_commands'] = len(loads)
    else:
        result['check_compliance_s'] = []
        result['switch_command_s'] = None

    if os.path.exists(REPORT):
        with open(REPORT) as handle:
            text = handle.read()
        shutil.copy(REPORT, os.path.join(out_dir, stem + '.report.md'))
        found = _violations(text)
        result['report'] = True
        result['violations'] = len(found)
        result['violation_lines'] = found[:10]
    else:
        result['report'] = False
        result['violations'] = None

    with open(os.path.join(prefix, 'checks.json')) as handle:
        result['checks'] = len(json.load(handle))
    with open(os.path.join(prefix, 'reach.txt')) as handle:
        result['policy_has_mutation'] = rule in handle.read()

    with open(os.path.join(prefix, 'SOURCE.json')) as handle:
        stamp = json.load(handle)
    result['input_files'] = stamp['files']
    result['drift_from_previous'] = stamp.get('drift_from_previous')
    for key in ('census', 'keep_every', 'lpm_sensitive_cells'):
        if key in stamp:
            result[key] = stamp[key]
    with open(os.path.join(prefix, 'checks.json')) as handle:
        compiled = json.load(handle)
    # The mutation turns ONE must-NOT-reach check into a must-reach; say so
    # rather than trust that editing the policy changed the question.
    # Both names followed by a space, so s2 does not also match s23.
    result['mutated_cell_check'] = [
        c for c in compiled if 'source.%s ' % cell[0] in c + ' '
        and 'probe.%s ' % cell[1] in c + ' ']

    # §3: a missing report or a missing check_compliance line is not a verdict.
    result['verdict_valid'] = (status == 'completed' and result['report']
                               and len(result['check_compliance_s']) == 1)

    with open(args.out, 'w') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({k: result[k] for k in (
        'workload', 'engine', 'mutated', 'status', 'wall_s', 'peak_rss_mb',
        'peak_rss_by_process_mb', 'switch_command_s',
        'check_compliance_s', 'violations', 'checks', 'drift_from_previous',
        'verdict_valid')}))
    if args.mutate:
        print("NOTE: artifacts under %s are MUTATED; regenerate with "
              "`bash test/gen_deltanet_inputs.sh`" % prefix, file=sys.stderr)
    return 0 if result['verdict_valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
