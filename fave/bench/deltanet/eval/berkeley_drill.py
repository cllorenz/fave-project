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

""" `wl_berkeley` on NDD-flood alone, as far as this machine carries it
(CLOUD_BENCH_PLAN.md §2.15; `results_berkeley_ndd_<date>/PROTOCOL.txt`).

The size series (`berkeley_series.py`) ran every engine with the inputs
regenerated inside each run and the JVM at its default heap. Past k=30 both
of those measure the harness rather than the engine: generation peaks at
~16 GB at full size in the SAME process that then sits beside the JVM, and the
default heap is a quarter of RAM. So here, per size:

1. generate the inputs ONCE, in a process of their own, sampled for time and
   peak RSS like a run (`gen_k<k>.json`);
2. run NDD on them with `--reuse-inputs` -- refused unless the stamp verifies
   -- an explicit `--jvm-xmx`, and the JVM's GC log.

A mutated run (s22 ---> s23, exactly 1 of 520 expected) is made at the
smallest drill size, and regenerates its own mutated inputs, so it runs BEFORE
that size's generation. The first size is an ANCHOR, already measured by the
series under the old settings, so the two settings can be compared on one
size. Sizes after the first failure are not attempted (§3's stopping rule),
and a step the remaining budget cannot cover is recorded as skipped.

Usage (from fave/, venv active):

    python3 bench/deltanet/eval/berkeley_drill.py --out DIR --budget 50400 \\
        --jvm-xmx 8g
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_run import _available_mb, _session_rss_mb  # noqa: E402

#: (keep_every, run deadline s, generation deadline s)
SIZES = ((30, 1800, 1800), (10, 3600, 1800), (3, 10800, 2700),
         (1, 28800, 3600))
MUTATION_SIZE = 10
MUTATION = 's22,s23'


def _write(out_dir, stem, record):
    with open(os.path.join(out_dir, stem + '.json'), 'w') as handle:
        json.dump(record, handle, indent=2)
        handle.write('\n')
    print(json.dumps(record))
    sys.stdout.flush()


def _generate(out_dir, keep_every, deadline, memory_floor):
    """ The inputs for one size, in their own sampled process. """
    started = time.time()
    with open(os.path.join(out_dir, 'gen_k%d.stdout' % keep_every), 'w') as log:
        # PYTHON, for the reason `bench/cell_run.py` spells out and
        # `bench/cloud_bdd_measure.py` already applies: every shell script in
        # this tree defaults to a bare `python3`
        # (`PYTHON="${PYTHON:-python3}"`), so without this the generator runs
        # on the SYSTEM interpreter and dies with `No module named 'filelock'`.
        # It cost phase B a start on 2026-10-06: the drill exited in 0.1 s at
        # k=30 and recorded `status: error`, which is an ENVIRONMENT failure
        # and not a result about the engine (§8.1).
        proc = subprocess.Popen(
            ['bash', 'test/gen_deltanet_inputs.sh', '--keep-every',
             str(keep_every), 'wl_berkeley'],
            env=dict(os.environ, PYTHON=sys.executable),
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        peak, least, status = 0, _available_mb(), None
        while status is None:
            try:
                status = 'completed' if proc.wait(timeout=1) == 0 else 'error'
                break
            except subprocess.TimeoutExpired:
                pass
            peak = max(peak, sum(_session_rss_mb(proc.pid).values()))
            least = min(least, _available_mb())
            if least < memory_floor:
                status = 'memory'
            elif time.time() - started > deadline:
                status = 'deadline'
            if status is not None:
                os.killpg(proc.pid, 9)
                proc.wait()
    record = {'step': 'generate', 'keep_every': keep_every, 'status': status,
              'wall_s': round(time.time() - started, 1), 'peak_rss_mb': peak,
              'least_available_mb': least, 'deadline_s': deadline}
    _write(out_dir, 'gen_k%d' % keep_every, record)
    return status == 'completed'


def _engine(out_dir, stem, keep_every, deadline, args, mutate=False):
    path = os.path.join(out_dir, stem + '.json')
    cmd = [sys.executable, 'bench/deltanet/eval/engine_run.py', 'wl_berkeley',
           '--backend', 'apkeep', '--engine', 'ndd',
           '--keep-every', str(keep_every), '--deadline', str(deadline),
           '--memory-floor', str(args.memory_floor),
           '--jvm-xmx', args.jvm_xmx, '--out', path]
    cmd += ['--mutate', '--mutate-cell', MUTATION] if mutate else ['--reuse-inputs']
    subprocess.run(cmd, check=False)
    with open(path) as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True)
    parser.add_argument('--budget', type=float, required=True, help='seconds')
    parser.add_argument('--jvm-xmx', required=True)
    parser.add_argument('--memory-floor', type=int, default=1500)
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    ends = time.time() + args.budget

    def skip(stem, keep_every, why):
        _write(args.out, stem, {'keep_every': keep_every, 'status': 'skipped',
                                'why': why})

    for keep_every, deadline, gen_deadline in SIZES:
        if keep_every == MUTATION_SIZE:
            stem = 'k%d_ndd_mut' % keep_every
            if ends - time.time() < deadline + gen_deadline:
                skip(stem, keep_every, 'budget')
            else:
                _engine(args.out, stem, keep_every, deadline, args, mutate=True)

        if ends - time.time() < deadline + gen_deadline:
            skip('k%d_ndd' % keep_every, keep_every, 'budget')
            break
        if not _generate(args.out, keep_every, gen_deadline, args.memory_floor):
            break
        result = _engine(args.out, 'k%d_ndd' % keep_every, keep_every,
                         deadline, args)
        if not result.get('verdict_valid'):
            break
    return 0


if __name__ == '__main__':
    sys.exit(main())
