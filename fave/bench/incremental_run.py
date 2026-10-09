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

""" ONE incremental stream on one engine -- INCREMENTAL_PLAN.md §5, §7.

Builds a workload from zero through the real aggregator path, answers every
check once, then drives an update stream (S1, S2, S3) at the adapter in batches
of `--batch` updates. Per batch it records, separately (D2):

* `t_update_s`   -- the engine applying the batch's updates, including the
                    invariant checks it runs by default (D1);
* `t_recheck_s`  -- re-verifying the checks the engine reported affected, and
                    merging them into the cached verdicts;
* `affected`     -- how many (source, probe) pairs it reported (None: unknown,
                    so every check was re-verified), and `rechecked`, the checks.

The compared number is their sum, `t_total_s`.

`--precision` additionally asks EVERY check after each batch -- untimed, and
outside both numbers -- to count the checks whose verdict actually changed, and
to fail the run if the selective re-verification missed one. That is the
oracle's first half (§5); the from-zero half is test/incremental_oracle.py's.

THIS IS A DEVELOPMENT DRIVER. It stamps `limit_class: dev` and enforces no
limit of its own: the per-update and per-stream limits are open question O4,
and no number from it is reportable until a PROTOCOL.txt with predictions has
been declared for the run (INCREMENTAL_PLAN.md §7).

Usage (from fave/, venv active):

    python3 bench/incremental_run.py bench/wl_ifi --engine netplumber \\
        --stream s2 --fraction 0.2 --seed 1 --batch 1 --precision \\
        --out /tmp/wl_ifi_np_s2.json
"""

import argparse
import datetime
import json
import logging
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

# pylint: disable=wrong-import-position
from bench.cell_metrics import limit_stamps
from bench.cell_run import engine_commit
from util import incremental as inc

ENGINES = ('netplumber', 'veriflow')
STREAMS = ('s1', 's2', 's3')


def make_engine(name):
    log = logging.getLogger("incremental_run")
    log.setLevel(logging.WARNING)
    if name == 'netplumber':
        from netplumber.lib_adapter import NetPlumberLibAdapter
        return lambda: NetPlumberLibAdapter(log)
    from veriflow.adapter import VeriFlowAdapter
    return lambda: VeriFlowAdapter(log)


def build_stream(kind, rules, links, fraction, seed):
    if kind == 's1':
        return list(inc.stream_s1(rules))
    if kind == 's2':
        return list(inc.stream_s2(rules, fraction, seed))
    return list(inc.stream_s3(links))


def quantiles(values):
    """ median, p90, p99, max of a list -- never a mean alone (§7). """
    if not values:
        return None
    ordered = sorted(values)
    def at(q):
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]
    return {'n': len(ordered), 'median': statistics.median(ordered),
            'p90': at(0.90), 'p99': at(0.99), 'max': ordered[-1]}


def run(args):
    make = make_engine(args.engine)
    checks = inc.load_checks(os.path.join(args.workload, 'checks.json'))
    engine = make()
    from util.in_process_driver import InProcessFaVe

    record = {
        'what': 'incremental stream (INCREMENTAL_PLAN.md §5, §7)',
        'workload': args.workload, 'engine': args.engine,
        'stream': args.stream, 'fraction': args.fraction, 'seed': args.seed,
        'batch': args.batch, 'precision': args.precision,
        'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                                   text=True, check=False).stdout.strip(),
        'engine_commit': engine_commit(
            'net_plumber' if args.engine == 'netplumber' else 'veriflow_fr'),
        **limit_stamps('dev', None, None, 'none'),
    }
    batches = []
    with InProcessFaVe(engine) as fave:
        t0 = time.perf_counter()
        fave.replay(args.workload)
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        previous = cache.full()
        record['build_and_first_check_s'] = time.perf_counter() - t0
        record['configuration'] = engine.configuration_stamp()
        rules, links = inc.model_rules(fave), inc.model_links(fave)
        stream = build_stream(args.stream, rules, links, args.fraction, args.seed)
        record.update({'checks': len(checks), 'rules': len(rules),
                       'links': len(links), 'updates': len(stream)})
        engine.take_affected()

        deleted, down = set(), set()
        missed = 0
        for start in range(0, len(stream), args.batch):
            batch = stream[start:start + args.batch]
            t_a = time.perf_counter()
            for update in batch:
                inc.apply(engine, update, deleted, down)
            t_b = time.perf_counter()
            affected = engine.take_affected()
            rechecked = cache.selective(affected)
            t_c = time.perf_counter()
            entry = {
                'ops': sorted({u[0] for u in batch}),
                'size': len(batch),
                't_update_s': t_b - t_a,
                't_recheck_s': t_c - t_b,
                't_total_s': t_c - t_a,
                'affected': None if affected is None else len(affected),
                'rechecked': len(rechecked),
            }
            if args.precision:
                full = cache.ask(checks)          # untimed
                entry['changed'] = sum(1 for c in full if full[c] != previous[c])
                entry['missed'] = sum(1 for c in full if full[c] != cache.verdict[c])
                missed += entry['missed']
                previous = full
            batches.append(entry)
            if args.limit_updates and start + len(batch) >= args.limit_updates:
                record['truncated_at'] = start + len(batch)
                break

    record['batches'] = batches
    record['summary'] = {
        't_total_s': quantiles([b['t_total_s'] for b in batches]),
        't_update_s': quantiles([b['t_update_s'] for b in batches]),
        't_recheck_s': quantiles([b['t_recheck_s'] for b in batches]),
        'rechecked': sum(b['rechecked'] for b in batches),
        'rechecked_if_full': len(batches) * len(checks),
    }
    if args.batch == 1:
        record['summary']['by_op'] = {
            op: quantiles([b['t_total_s'] for b in batches if b['ops'] == [op]])
            for op in ('insert', 'delete', 'link_down', 'link_up')
            if any(b['ops'] == [op] for b in batches)}
    if args.precision:
        changed = sum(b['changed'] for b in batches)
        record['summary'].update({
            'changed': changed, 'missed': missed,
            'precision': (changed / record['summary']['rechecked']
                          if record['summary']['rechecked'] else None)})
    record['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return record, missed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('workload', help="the workload directory, e.g. bench/wl_ifi")
    parser.add_argument('--engine', choices=ENGINES, required=True)
    parser.add_argument('--stream', choices=STREAMS, required=True)
    parser.add_argument('--fraction', type=float, default=0.2,
                        help="S2: the share of rules deleted and re-added")
    parser.add_argument('--seed', type=int, default=1, help="S2: the stated seed")
    parser.add_argument('--batch', type=int, default=1,
                        help="updates per re-verification (D4)")
    parser.add_argument('--precision', action='store_true',
                        help="also ask every check after each batch (untimed)")
    parser.add_argument('--limit-updates', type=int, default=0,
                        help="stop after this many updates (0: the whole stream)")
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.batch < 1:
        parser.error("--batch must be at least 1")

    record, missed = run(args)
    with open(args.out, 'w') as handle:
        json.dump(record, handle, indent=1, sort_keys=True)
    print(json.dumps(record['summary'], indent=1, sort_keys=True))
    if missed:
        print("SELECTIVE RE-VERIFICATION MISSED %d CHANGED VERDICTS" % missed,
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
