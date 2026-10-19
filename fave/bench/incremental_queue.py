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

""" A queue of incremental cells, run IN PARALLEL under a memory budget, and
RESUMABLE -- for the D11 run (INCREMENTAL_PLAN.md §4), which is too large to
run one cell at a time.

`bench/cell_queue.py`'s rule, for incremental cells: a cell whose result is a
measurement or a DECLARED limit (outcome `did_not_finish`: its wall or memory
limit stopped it) is done and skipped on a restart; one that was `interrupted`,
or left no result, is run again, its old directory first moved to
`_interrupted/` (kept, never deleted: `incremental_cell.py` never overwrites). A cell
that ended in `error` or `oracle_failed` is NOT re-run: a crash is a finding to
be looked at, never retried into a number -- it is listed at the end.

The queue file is a JSON list. Per cell: `name`, `workload`, `engine`,
`stream`, `mem_mb` (the memory the cell may hold: it is the cell's RSS limit,
and the scheduler keeps the running cells' sum within `--mem-budget`), and
`est_h` (an estimate of its wall time: the longest go first). Every other key
is passed to `bench/incremental_cell.py` as `--key value` (a bare `--key` for
`true`).

Usage (from fave/, venv active):

    python3 bench/incremental_queue.py --queue d11.json --out-dir <run>/cells \\
        --jobs 8 --mem-budget 48000
    python3 bench/incremental_queue.py ... --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
import time

from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))

#: outcomes that are a result: skipped on a restart
DONE = ('measured', 'did_not_finish', 'refused')
#: outcomes that are a finding: not re-run, listed
FLAGGED = ('error', 'oracle_failed', 'machine_stop')
_OWN = ('name', 'workload', 'engine', 'stream', 'mem_mb', 'est_h',
        'limit-rss', 'memory-floor', 'alone', 'recorded')
#: the queue's defaults for every cell (`main`): None keeps the cell's
#: reservation as its RSS limit, as before INCREMENTAL_PLAN.md D17.5
LIMITS: Dict[str, Optional[int]] = {'limit-rss': None, 'memory-floor': None}


def state(cell_dir: str) -> Optional[str]:
    """ The outcome a cell directory records, or None if it has none. """
    path = os.path.join(cell_dir, 'rep01', 'cell.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path) as raw:
            return json.load(raw).get('outcome')
    except (OSError, ValueError):
        return None


def command(cell: Dict[str, Any], out_dir: str, python: str) -> List[str]:
    """ The cell's command line. `mem_mb` is what the cell RESERVES in the
    queue's budget; its RSS limit is the cell's `limit-rss`, else the
    queue's (`--limit-rss`, V5's 32 GB class for the campaign, D17.5), else
    the reservation. """
    rss = cell.get('limit-rss', LIMITS['limit-rss'] or cell['mem_mb'])
    floor = cell.get('memory-floor', LIMITS['memory-floor'])
    argv = [python, os.path.join(HERE, 'incremental_cell.py'), cell['workload'],
            '--engine', cell['engine'], '--stream', cell['stream'],
            '--limit-rss', str(rss),
            '--out', os.path.join(out_dir, cell['name'])]
    if floor is not None:
        argv += ['--memory-floor', str(floor)]
    for key in sorted(cell):
        if key in _OWN:
            continue
        value = cell[key]
        if value is True:
            argv.append('--' + key)
        elif value is not False and value is not None:
            argv += ['--' + key, str(value)]
    return argv


def retire(out_dir: str, name: str) -> Optional[str]:
    """ Move a cell's unfinished directory (interrupted, or no result) to
    `_interrupted/<name>.<time>`, so the cell can run again. """
    d = os.path.join(out_dir, name)
    if not os.path.exists(d):
        return None
    away = os.path.join(out_dir, '_interrupted', '%s.%s' % (name, time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())))
    os.makedirs(os.path.dirname(away), exist_ok=True)
    os.rename(d, away)
    return away


def plan(cells: List[Dict[str, Any]], out_dir: str) -> List[Dict[str, Any]]:
    """ The cells still to run, longest first. """
    todo = []
    for cell in cells:
        st = state(os.path.join(out_dir, cell['name']))
        if st in DONE or st in FLAGGED:
            continue
        todo.append(cell)
    return sorted(todo, key=lambda c: -float(c.get('est_h', 0)))


def core_groups(jobs: int, cpus: Optional[List[int]] = None) -> List[List[int]]:
    """ The machine's cores in `jobs` disjoint groups of equal size, one per
    parallel cell (INCREMENTAL_PLAN.md D17.8); a remainder stays unused. """
    cpus = sorted(cpus if cpus is not None else os.sched_getaffinity(0))
    size = len(cpus) // jobs
    if size < 1:
        raise ValueError("%d cores cannot be split into %d groups" % (len(cpus), jobs))
    return [cpus[i * size:(i + 1) * size] for i in range(jobs)]


def pinned(argv: List[str], group: Optional[List[int]]) -> List[str]:
    """ `argv` run on the cores of `group` (all of them when None). """
    if not group:
        return argv
    return ['taskset', '-c', ','.join(str(c) for c in group)] + argv


def record(cell: Dict[str, Any], out_dir: str) -> None:
    """ A cell that is RECORDED, not run (INCREMENTAL_PLAN.md D17.10): its
    `recorded` entry -- the outcome, the limit it stands for, its basis --
    written as the cell's result, marked as recorded. """
    d = os.path.join(out_dir, cell['name'], 'rep01')
    os.makedirs(d, exist_ok=True)
    entry = dict(cell['recorded'])
    with open(os.path.join(d, 'cell.json'), 'w') as handle:
        json.dump(dict(entry, recorded=True, name=cell['name'], workload=cell['workload'],
                       engine=cell['engine'], stream=cell['stream'], completed_updates=0),
                  handle, indent=1, sort_keys=True)


def run(cells: List[Dict[str, Any]], out_dir: str, jobs: int, budget: int,
        python: str, log, pin: bool = False) -> List[str]:
    """ Run `cells`, at most `jobs` at a time within `budget` MB of
    reservations; with `pin`, each on its own group of cores, a JVM's
    collector set to its size (FAVE_JVM_GC_THREADS). A cell marked `alone`
    starts only when nothing runs, has the whole machine unpinned, and
    nothing starts beside it. """
    todo = plan(cells, out_dir)
    for cell in [c for c in todo if c.get('recorded')]:
        todo.remove(cell)
        record(cell, out_dir)
        log("%s recorded %s (%s, not run: %s)" % (
            _now(), cell['name'], cell['recorded'].get('outcome'),
            cell['recorded'].get('basis', '')))
    running: Dict[str, Any] = {}
    used = 0
    free = core_groups(jobs) if pin else []
    while todo or running:
        # start what fits: the longest that fits the budget, while slots remain
        started = True
        alone_running = any(c.get('alone') for _p, c, _h, _t, _g in running.values())
        while started and todo and len(running) < jobs and not alone_running:
            started = False
            for cell in todo:
                if cell.get('alone') and running:
                    continue
                if used + int(cell['mem_mb']) <= budget or not running:
                    # (a cell larger than the budget runs alone)
                    todo.remove(cell)
                    retire(out_dir, cell['name'])
                    os.makedirs(out_dir, exist_ok=True)
                    handle = open(os.path.join(out_dir, cell['name'] + '.log'), 'w')
                    group = free.pop(0) if pin and not cell.get('alone') else None
                    env = dict(os.environ)
                    if group:
                        env['FAVE_JVM_GC_THREADS'] = str(len(group))
                    proc = subprocess.Popen(pinned(command(cell, out_dir, python), group),
                                            cwd=os.path.dirname(HERE), env=env,
                                            stdout=handle, stderr=subprocess.STDOUT)
                    running[cell['name']] = (proc, cell, handle, time.time(), group)
                    used += int(cell['mem_mb'])
                    log("%s start %s (%d MB, est %.2f h; running %d, %d MB%s)" % (
                        _now(), cell['name'], cell['mem_mb'], float(cell.get('est_h', 0)),
                        len(running), used,
                        '; cores %s' % ','.join(map(str, group)) if group else
                        ('; alone' if cell.get('alone') else '')))
                    started = True
                    alone_running = bool(cell.get('alone'))
                    break
        time.sleep(2)
        for name in list(running):
            proc, cell, handle, t0, group = running[name]
            if proc.poll() is None:
                continue
            handle.close()
            used -= int(cell['mem_mb'])
            if group:
                free.append(group)
            del running[name]
            log("%s end   %s rc=%d outcome=%s after %.2f h" % (
                _now(), name, proc.returncode, state(os.path.join(out_dir, name)),
                (time.time() - t0) / 3600))
    return [c['name'] for c in cells
            if state(os.path.join(out_dir, c['name'])) in FLAGGED]


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--queue', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--mem-budget', type=int, required=True,
                        help="MB the running cells may hold together")
    parser.add_argument('--limit-rss', type=int, default=None,
                        help="every cell's RSS limit in MB unless the cell sets "
                             "its own (default: the cell's mem_mb reservation)")
    parser.add_argument('--memory-floor', type=int, default=None,
                        help="every cell's available-memory floor in MB unless "
                             "the cell sets its own (default: incremental_cell's)")
    parser.add_argument('--pin', action='store_true',
                        help="each cell on its own group of cores (D17.8)")
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    LIMITS.update({'limit-rss': args.limit_rss, 'memory-floor': args.memory_floor})
    with open(args.queue) as raw:
        cells = json.load(raw)
    names = [c['name'] for c in cells]
    if len(set(names)) != len(names):
        parser.error("duplicate cell names in the queue")
    for c in cells:
        missing = [k for k in ('name', 'workload', 'engine', 'stream', 'mem_mb') if k not in c]
        if missing:
            parser.error("cell %r lacks %s" % (c.get('name'), missing))
    if args.dry_run:
        for cell in plan(cells, args.out_dir):
            print(' '.join(command(cell, args.out_dir, args.python)))
        return 0
    flagged = run(cells, args.out_dir, args.jobs, args.mem_budget, args.python,
                  lambda line: print(line, flush=True), pin=args.pin)
    if flagged:
        print("FLAGGED (error / oracle_failed / machine_stop), not re-run: %s"
              % ', '.join(flagged))
    return 0


if __name__ == '__main__':
    sys.exit(main())
