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

""" `wl_berkeley`'s size series, as its protocol declares it
(CLOUD_BENCH_PLAN.md §2.15; `results_berkeley_<date>/PROTOCOL.txt`).

A script and not shell history, so the figures are re-derivable (§1.8). One
`engine_run.py` per cell, results under `--out`:

1. non-vacuity first: one MUTATED run per engine at the smallest size,
   permitting 22 -> 23, the one off-diagonal cell the walk finds unreached --
   expected exactly 1 violation of 520;
2. then the plain series, sizes large-k first and engines interleaved at each
   size, so machine drift is spread across engines rather than aligned with
   one of them. An engine leaves the series at its first run that is not a
   valid verdict -- deadline, memory, error -- and is not retried: a bigger
   model will not do better (§3's stopping rule).

A run starts only if the remaining budget covers its whole deadline; a run
that cannot is recorded as `status: skipped`, so a gap in the table is never
silent.

Usage (from fave/, venv active, net_plumber on PATH):

    python3 bench/deltanet/eval/berkeley_series.py --out DIR --budget 21600
"""

import argparse
import json
import os
import subprocess
import sys
import time

ENGINES = (('netplumber', None), ('apkeep', 'ndd'), ('apkeep', 'bdd'))
SIZES = (1000, 300, 100, 30, 10, 3, 1)
MUTATION = 's22,s23'


def _label(backend, engine):
    return engine or backend


def _run(out_dir, stem, backend, engine, keep_every, deadline, mutate):
    path = os.path.join(out_dir, stem + '.json')
    cmd = [sys.executable, 'bench/deltanet/eval/engine_run.py', 'wl_berkeley',
           '--backend', backend, '--keep-every', str(keep_every),
           '--deadline', str(deadline), '--out', path]
    if engine:
        cmd += ['--engine', engine]
    if mutate:
        cmd += ['--mutate', '--mutate-cell', MUTATION]
    subprocess.run(cmd, check=False)
    with open(path) as handle:
        return json.load(handle)


def _skip(out_dir, stem, backend, engine, keep_every, why):
    with open(os.path.join(out_dir, stem + '.json'), 'w') as handle:
        json.dump({'workload': 'wl_berkeley', 'backend': backend,
                   'engine': _label(backend, engine), 'keep_every': keep_every,
                   'status': 'skipped', 'why': why}, handle, indent=2)
        handle.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True)
    parser.add_argument('--budget', type=float, required=True, help='seconds')
    parser.add_argument('--deadline', type=float, default=3600)
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    ends = time.time() + args.budget

    def fits():
        return ends - time.time() >= args.deadline

    for backend, engine in ENGINES:
        stem = 'k%d_%s_mut' % (SIZES[0], _label(backend, engine))
        if not fits():
            _skip(args.out, stem, backend, engine, SIZES[0], 'budget')
            continue
        _run(args.out, stem, backend, engine, SIZES[0], args.deadline, True)

    active = list(ENGINES)
    for keep_every in SIZES:
        for backend, engine in list(active):
            stem = 'k%d_%s' % (keep_every, _label(backend, engine))
            if not fits():
                _skip(args.out, stem, backend, engine, keep_every, 'budget')
                continue
            result = _run(args.out, stem, backend, engine, keep_every,
                          args.deadline, False)
            if not result.get('verdict_valid'):
                active.remove((backend, engine))
    return 0


if __name__ == '__main__':
    sys.exit(main())
