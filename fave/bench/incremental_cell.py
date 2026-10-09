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

""" ONE incremental cell under declared limits, repeated -- INCREMENTAL_PLAN.md
O3, O4.

Runs `bench/incremental_run.py` as a child, through `cell_run.run_cell`, under
the three stopping rules O4 names, each stamped:

* `--limit-wall`    the stream's wall clock (the cell's limit);
* `--limit-rss`     summed RSS; with `--memory-floor`, the harness stops the run
                    before the kernel's OOM killer would pick a victim;
* `--limit-update`  the per-update hang guard: the child flushes a record per
                    batch, and the run is stopped when none has come for this
                    long (O4.3).

A stream a limit stops reports its completed prefix, "n of N", as a
did-not-finish (O4.2); the raw records up to the stop are kept. Each of
`--repetitions` runs goes into `<out>/repNN/` with its own `cell.json`
(stamps, the run's measurements, the outcome), and the raw files are gzip'd
afterwards (owner, 2026-10-09: keep the raw data).

**Defaults are the indicative runs' (owner, 2026-10-09):** `limit_class=dev`,
one repetition, the machine's memory (no swap here) as the RSS limit, 24 h
wall, 1 h per update. A complete campaign sets its own (O4: V5's class, ten
repetitions per seed) -- and a `PROTOCOL.txt` with predictions first.

Usage (from fave/, venv active):

    python3 bench/incremental_cell.py bench/wl_ifi --engine netplumber \\
        --stream s2 --fraction 0.2 --seed 1 --out results/inc/wl_ifi_np_s2
"""

import argparse
import gzip
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

# pylint: disable=wrong-import-position
from bench import cell_metrics
from bench.cell_run import run_cell
from bench.incremental_run import ENGINES, STREAMS
from bench.incremental_report import read_lines

_DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'incremental_run.py')
_RAW = ('stream.jsonl', 'updates.jsonl', 'oracle.jsonl')


def child_argv(args, cell_dir):
    argv = [sys.executable, _DRIVER, args.workload, '--engine', args.engine,
            '--stream', args.stream, '--fraction', str(args.fraction),
            '--seed', str(args.seed), '--batch', str(args.batch),
            '--checks', args.checks, '--cell-dir', cell_dir]
    if args.files:
        argv += ['--files', args.files]
    if args.limit_updates:
        argv += ['--limit-updates', str(args.limit_updates)]
    if args.oracle_sample:
        argv += ['--oracle-sample', str(args.oracle_sample),
                 '--oracle-every', str(args.oracle_every),
                 '--oracle-seed', str(args.oracle_seed)]
    return argv


def gzip_raw(cell_dir):
    """ Compress the raw files in place; the plain ones are removed only once
    their compressed copy is complete. """
    for name in _RAW:
        plain = os.path.join(cell_dir, name)
        if not os.path.exists(plain):
            continue
        with open(plain, 'rb') as src, gzip.open(plain + '.gz', 'wb') as dst:
            shutil.copyfileobj(src, dst)
        os.remove(plain)


def outcome(measured, end):
    """ What the cell says about the engine. An oracle failure is a defect,
    told apart from an `error`; everything else is `cell_metrics.outcome`'s
    distinction: a declared limit is a did-not-finish (a result, with its
    prefix), the environment's kill is `interrupted` (re-run). """
    if end and end.get('status') == 'oracle_failed':
        return 'oracle_failed'
    return cell_metrics.outcome(measured['status'], measured['status'] == 'completed')


def run_repetition(args, rep):
    cell_dir = os.path.join(args.out, 'rep%02d' % rep)
    if os.path.exists(cell_dir):
        raise SystemExit("%s exists: a cell is never overwritten" % cell_dir)
    os.makedirs(cell_dir)
    measured = run_cell(
        child_argv(args, cell_dir), {}, args.limit_wall, args.limit_rss,
        args.memory_floor, args.status_every, os.path.join(cell_dir, 'cell.json'),
        stall_path=os.path.join(cell_dir, 'updates.jsonl'),
        limit_stall_s=args.limit_update)
    end_path = os.path.join(cell_dir, 'end.json')
    end = None
    if os.path.exists(end_path):
        with open(end_path) as handle:
            end = json.load(handle)
    done = sum(r['n'] for r in read_lines(os.path.join(cell_dir, 'updates.jsonl')))
    record = {
        'what': 'incremental cell (INCREMENTAL_PLAN.md O3, O4)',
        **cell_metrics.limit_stamps(args.limit_class, args.limit_wall,
                                    args.limit_rss, measured['limit_tripped']),
        'limit_update_s': args.limit_update,
        'memory_floor_mb': args.memory_floor,
        'repetition': rep, 'repetitions': args.repetitions,
        'argv': child_argv(args, cell_dir)[1:],
        'measured': measured,
        'completed_updates': done,
        'outcome': outcome(measured, end),
    }
    with open(os.path.join(cell_dir, 'cell.json'), 'w') as handle:
        json.dump(record, handle, indent=1, sort_keys=True)
    gzip_raw(cell_dir)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('workload')
    parser.add_argument('--engine', choices=ENGINES, required=True)
    parser.add_argument('--stream', choices=STREAMS, required=True)
    parser.add_argument('--fraction', type=float, default=0.2)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--batch', type=int, default=1)
    parser.add_argument('--files', default=None)
    parser.add_argument('--checks', default='checks.json')
    parser.add_argument('--limit-updates', type=int, default=0)
    parser.add_argument('--oracle-sample', type=int, default=0)
    parser.add_argument('--oracle-every', type=int, default=0)
    parser.add_argument('--oracle-seed', type=int, default=1)
    parser.add_argument('--limit-class', choices=('dev', 'v5'), default='dev')
    parser.add_argument('--limit-wall', type=float, default=86400.0)
    parser.add_argument('--limit-rss', type=int, default=None,
                        help="MB; default: the machine's memory")
    parser.add_argument('--memory-floor', type=int, default=1024,
                        help="MB of MemAvailable below which the run is stopped")
    parser.add_argument('--limit-update', type=float, default=3600.0,
                        help="seconds without a completed batch (O4.3)")
    parser.add_argument('--status-every', type=float, default=60.0)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--out', required=True, help="the cell's directory")
    args = parser.parse_args(argv)
    if args.limit_rss is None:
        args.limit_rss = cell_metrics.machine()['ram_mb']
    if args.limit_class == 'v5' and (args.limit_wall > 86400 or args.limit_rss > 32768):
        parser.error("limit class v5 is at most 24 h and 32 GB (MEASUREMENT_RUN_PLAN.md §2)")
    os.makedirs(args.out, exist_ok=True)
    worst = 0
    for rep in range(1, args.repetitions + 1):
        record = run_repetition(args, rep)
        print(json.dumps({'repetition': rep, 'outcome': record['outcome'],
                          'completed_updates': record['completed_updates'],
                          'wall_s': record['measured']['wall_s']}))
        if record['outcome'] in ('error', 'oracle_failed', 'interrupted'):
            worst = 1
    return worst


if __name__ == '__main__':
    sys.exit(main())
