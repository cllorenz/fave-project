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

""" A campaign of cells, run consecutively, and RESUMABLE.

`MEASUREMENT_RUN_PLAN.md` §6.1. The measuring machine is a container, in a VM,
on a shared server; the 2026-09-29 sandbox death is in `CLOUD_BENCH_PLAN.md`
§2.15's open list with no cause found. A two-day campaign that has to be
restarted from the beginning after each of those is not a campaign.

So: each cell writes its own result, and a restart SKIPS every cell that already
has one and resumes at the first that does not. The campaign must survive being
started three times and produce the same set of results.

THE ONE JUDGEMENT THIS MAKES, and it is the distinction the stopping-rule
discipline rests on: a cell whose result says `interrupted` -- or which left a
progress trail but no result at all, which is what a container death looks like
from outside -- is **not done**. It is re-run. A cell killed by a DECLARED limit
(`deadline`, `memory`) **is** done: that is a result, and re-running it would
replace a measurement with an identical one.

Each cell is a subprocess, so a cell that dies on its own does not take the
queue with it.

The queue file is a JSON list; every key but `name` is passed to
`bench/cell_run.py` as `--key value` (or a bare `--key` for `true`):

    [{"name": "stanford_ndd", "workload": "wl_stanford",
      "backend": "apkeep", "apkeep-engine": "ndd",
      "limit-class": "v5", "limit-wall": 86400, "limit-rss": 32768}]

Usage (from fave/, venv active):

    python3 bench/cell_queue.py --queue campaign.json --out-dir results/v5
    python3 bench/cell_queue.py --queue campaign.json --out-dir results/v5 --dry-run
"""

import argparse
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: A result in one of these states is FINAL -- the cell is not re-run.
#: `deadline` and `memory` are results: a declared limit tripped, which is what
#: a did-not-finish cell IS. `interrupted` is deliberately absent.
FINAL = ('completed', 'error', 'deadline', 'memory')


def state_of(out_dir, name):
    """ `(state, detail)` for one cell: what a restart needs to decide.

    * `done` -- a result exists and is final.
    * `interrupted` -- a result says so, OR a progress trail exists with no
      result beside it, which is what a container death looks like from the
      outside: the runner never got to write anything.
    * `todo` -- nothing there.
    """
    result = os.path.join(out_dir, name + '.json')
    trail = os.path.join(out_dir, name + '.status.jsonl')
    if os.path.exists(result):
        try:
            with open(result) as handle:
                stored = json.load(handle)
        except (ValueError, OSError):
            return 'interrupted', 'result file is not readable JSON'
        status = stored.get('status')
        if status in FINAL:
            return 'done', status
        return 'interrupted', 'status=%s' % status
    if os.path.exists(trail):
        return 'interrupted', 'progress trail with no result'
    return 'todo', None


def cell_argv(cell, out_dir):
    """ One cell spec -> a `cell_run.py` command line. """
    name = cell['name']
    argv = [sys.executable, os.path.join(HERE, 'cell_run.py'), cell['workload']]
    for key, value in sorted(cell.items()):
        if key in ('name', 'workload'):
            continue
        if value is True:
            argv.append('--%s' % key)
        elif value is False or value is None:
            continue
        elif str(value).startswith('-'):
            # `--key=value`, because the queue spawns without a shell and a
            # VALUE that looks like an option is ambiguous to argparse. It
            # survives today only by a heuristic -- argparse treats a token
            # containing a space as a value -- so `--engine-options "--solver
            # cadical195"` happens to work and a single-token
            # `--engine-options "--lite-acyclic"` would be read as a flag and
            # refused. The `=` form has no such edge.
            argv.append('--%s=%s' % (key, value))
        else:
            argv += ['--%s' % key, str(value)]
    argv += ['--out', os.path.join(out_dir, name + '.json')]
    return argv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--queue', required=True, help='the JSON cell list')
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--dry-run', action='store_true',
                        help='print what would run, and what would be skipped')
    parser.add_argument('--retry-interrupted', action='store_true',
                        default=True, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    with open(args.queue) as handle:
        cells = json.load(handle)
    names = [c['name'] for c in cells]
    if len(set(names)) != len(names):
        raise SystemExit('two cells share a name, so one would overwrite the '
                         "other's result: %s" % names)

    os.makedirs(args.out_dir, exist_ok=True)
    done = ran = failed = 0
    for cell in cells:
        state, detail = state_of(args.out_dir, cell['name'])
        if state == 'done':
            print('[skip] %-28s already %s' % (cell['name'], detail))
            done += 1
            continue
        if state == 'interrupted':
            print('[redo] %-28s %s' % (cell['name'], detail))
        command = cell_argv(cell, args.out_dir)
        if args.dry_run:
            print('[would run] %s'
                  % ' '.join(shlex.quote(c) for c in command))
            continue
        print('[run ] %-28s %s' % (cell['name'], ' '.join(command[2:])))
        sys.stdout.flush()
        rc = subprocess.run(command, check=False).returncode
        ran += 1
        if rc != 0:
            failed += 1
            # NOT fatal: `MEASUREMENT_RUN_PLAN.md` §8.1 -- a cell that fails for
            # an engine reason is recorded and the campaign continues. Stopping
            # the queue to debug one engine costs every cell behind it.
            print('[warn] %s exited %d; recorded and continuing'
                  % (cell['name'], rc))
    print('queue: %d skipped, %d run, %d of those non-zero' % (done, ran, failed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
