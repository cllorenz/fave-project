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
                    `--limit-rss-margin` instead sets it, per repetition, to
                    the memory available at the start less the margin, for a
                    cell that runs alone (below);
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
    if args.footprint:
        argv += ['--footprint', args.footprint]
    if args.expect_violations is not None:
        argv += ['--expect-violations', str(args.expect_violations)]
    if args.engine == 'ad6':
        argv += ['--ad6-grounding', args.ad6_grounding, '--ad6-solver', args.ad6_solver]
        if args.ad6_lite_acyclic:
            argv.append('--ad6-lite-acyclic')
    if args.ndd_collect_visited:
        argv.append('--ndd-collect-visited')
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
    if measured.get('memory_stop') == 'memory_floor':
        # the MACHINE ran low (cells sharing it grew together), not this
        # cell's limit: not a did-not-finish (INCREMENTAL_PLAN.md D17.5)
        return 'machine_stop'
    if end and end.get('status') == 'refused':
        # S4: an edit the engine could not take; the stream stops there and
        # reports its prefix, like a limit -- a result, not a crash
        return 'refused'
    return cell_metrics.outcome(measured['status'], measured['status'] == 'completed')


def rss_limit(args, available_mb=None):
    """ The repetition's RSS limit in MB and what it was derived from.

    A cell that runs alone may hold the whole machine, but not the machine's
    RAM: the k = 1 trial's limit was the RAM less 2 GB (62,246 MB) while
    59,831 MB were available at its start, so the kernel's OOM killer ended
    it before its limit could, and a memory stop was recorded as an `error`
    (results_ndd_berkeley_k1_trial_20261020/FINDINGS.txt). With
    `--limit-rss-margin` the limit is what is available when the repetition
    starts, less the margin, so the cell's own limit comes first. """
    if args.limit_rss_margin is None:
        return args.limit_rss, {'declared_mb': args.limit_rss}
    if available_mb is None:
        available_mb = cell_metrics.available_mb()
    limit = available_mb - args.limit_rss_margin
    if limit <= 0:
        raise SystemExit("%d MB available, less a margin of %d MB, leaves no "
                         "memory for the cell" % (available_mb, args.limit_rss_margin))
    return limit, {'available_at_start_mb': available_mb,
                   'margin_mb': args.limit_rss_margin}


def run_repetition(args, rep):
    cell_dir = os.path.join(args.out, 'rep%02d' % rep)
    if os.path.exists(cell_dir):
        raise SystemExit("%s exists: a cell is never overwritten" % cell_dir)
    os.makedirs(cell_dir)
    # D17.7: a JVM engine's collections, as V5's cells record them
    gc_log = os.path.join(cell_dir, 'gc.log')
    env = {'FAVE_JVM_GC_LOG': gc_log} if args.engine in ('apkeep', 'ndd-apkeep') else {}
    if args.jvm_xmx:
        # the heap cap, for the JVM engines; without it the JVM's default (a
        # quarter of RAM) holds, below NDD-APKeep's live data at wl_berkeley
        # k = 1 (results_python_memory_20261021/FINDINGS_k1.txt)
        env['FAVE_JVM_XMX'] = args.jvm_xmx
    limit_rss, basis = rss_limit(args)
    measured = run_cell(
        child_argv(args, cell_dir), env, args.limit_wall, limit_rss,
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
                                    limit_rss, measured['limit_tripped']),
        'limit_rss_basis': basis,
        'limit_update_s': args.limit_update,
        'memory_floor_mb': args.memory_floor,
        'jvm_xmx': args.jvm_xmx,
        'repetition': rep, 'repetitions': args.repetitions,
        'argv': child_argv(args, cell_dir)[1:],
        'measured': measured,
        'completed_updates': done,
        'outcome': outcome(measured, end),
        'gc': cell_metrics.gc_summary(gc_log) if os.path.exists(gc_log) else None,
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
    parser.add_argument('--expect-violations', type=int, default=None,
                        help="the workload's declared violation count (D17.6)")
    parser.add_argument('--ad6-grounding', default='rank')
    parser.add_argument('--ad6-solver', default='cadical195')
    parser.add_argument('--ad6-lite-acyclic', action='store_true')
    parser.add_argument('--ndd-collect-visited', action='store_true',
                        help="passed to incremental_run.py (NDD-APKeep only)")
    parser.add_argument('--oracle-sample', type=int, default=0)
    parser.add_argument('--oracle-every', type=int, default=0)
    parser.add_argument('--oracle-seed', type=int, default=1)
    parser.add_argument('--footprint', default=None,
                        help="passed to incremental_run.py (witness, dead-ends, "
                             "or coarse; default both)")
    parser.add_argument('--limit-class', choices=('dev', 'v5'), default='dev')
    parser.add_argument('--limit-wall', type=float, default=86400.0)
    parser.add_argument('--limit-rss', type=int, default=None,
                        help="MB; default: the machine's memory")
    parser.add_argument('--limit-rss-margin', type=int, default=None,
                        help="MB: the RSS limit is the memory available at each "
                             "repetition's start less this (a cell run alone); "
                             "replaces --limit-rss")
    parser.add_argument('--jvm-xmx', default=None,
                        help="the JVM engines' heap cap (FAVE_JVM_XMX, e.g. 32g); "
                             "default: the environment's, else the JVM's")
    parser.add_argument('--memory-floor', type=int, default=1024,
                        help="MB of MemAvailable below which the run is stopped")
    parser.add_argument('--limit-update', type=float, default=3600.0,
                        help="seconds without a completed batch (O4.3)")
    parser.add_argument('--status-every', type=float, default=60.0)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--out', required=True, help="the cell's directory")
    args = parser.parse_args(argv)
    if args.limit_rss_margin is not None:
        if args.limit_rss is not None:
            parser.error("--limit-rss and --limit-rss-margin exclude each other")
        if args.limit_class == 'v5':
            parser.error("limit class v5 declares its RSS limit (32 GB), not a margin")
    elif args.limit_rss is None:
        args.limit_rss = cell_metrics.machine()['ram_mb']
    if args.limit_class == 'v5' and (args.limit_wall > 86400 or (args.limit_rss or 0) > 32768):
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
