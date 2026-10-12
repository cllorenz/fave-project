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
FLAGGED = ('error', 'oracle_failed')
_OWN = ('name', 'workload', 'engine', 'stream', 'mem_mb', 'est_h')


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
    argv = [python, os.path.join(HERE, 'incremental_cell.py'), cell['workload'],
            '--engine', cell['engine'], '--stream', cell['stream'],
            '--limit-rss', str(cell['mem_mb']),
            '--out', os.path.join(out_dir, cell['name'])]
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


def run(cells: List[Dict[str, Any]], out_dir: str, jobs: int, budget: int,
        python: str, log) -> List[str]:
    todo = plan(cells, out_dir)
    running: Dict[str, Any] = {}
    used = 0
    while todo or running:
        # start what fits: the longest that fits the budget, while slots remain
        started = True
        while started and todo and len(running) < jobs:
            started = False
            for cell in todo:
                if used + int(cell['mem_mb']) <= budget or not running:
                    # (a cell larger than the budget runs alone)
                    todo.remove(cell)
                    retire(out_dir, cell['name'])
                    os.makedirs(out_dir, exist_ok=True)
                    handle = open(os.path.join(out_dir, cell['name'] + '.log'), 'w')
                    proc = subprocess.Popen(command(cell, out_dir, python), cwd=os.path.dirname(HERE),
                                            stdout=handle, stderr=subprocess.STDOUT)
                    running[cell['name']] = (proc, cell, handle, time.time())
                    used += int(cell['mem_mb'])
                    log("%s start %s (%d MB, est %.2f h; running %d, %d MB)" % (
                        _now(), cell['name'], cell['mem_mb'], float(cell.get('est_h', 0)),
                        len(running), used))
                    started = True
                    break
        time.sleep(2)
        for name in list(running):
            proc, cell, handle, t0 = running[name]
            if proc.poll() is None:
                continue
            handle.close()
            used -= int(cell['mem_mb'])
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
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
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
                  lambda line: print(line, flush=True))
    if flagged:
        print("FLAGGED (error / oracle_failed), not re-run: %s" % ', '.join(flagged))
    return 0


if __name__ == '__main__':
    sys.exit(main())
