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

""" The tables of an incremental run, generated from its raw records --
INCREMENTAL_PLAN.md §7, O5 ("quantiles, ratios and tables are generated from
these files, never typed").

Reads a directory of cells named `<workload>_<engine>_<stream>` (each with
`rep01/`, as `bench/incremental_cell.py` writes them), summarises every cell
with `incremental_report.summarize`, checks every (workload, stream) across
its engines with `incremental_compare.compare`, and writes `summary.json` and a
Markdown table. Times in milliseconds.

Usage (from fave/):

    python3 bench/incremental_table.py bench/campaigns/<run>/cells --md table.md
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

# pylint: disable=wrong-import-position
from bench.incremental_compare import compare
from bench.incremental_report import load_cell, summarize

_ENGINES = ('netplumber', 'veriflow', 'apkeep')


def _ms(q, key):
    return None if not q or q.get(key) is None else round(1000 * q[key], 2)


def _ratio(x):
    return '-' if x is None else '%.3f' % x


def collect(cells_dir):
    cells = {}
    for name in sorted(os.listdir(cells_dir)):
        rep = os.path.join(cells_dir, name, 'rep01')
        if not os.path.isdir(rep):
            continue
        # <workload>_<engine>_<stream>; the workload's own name has '_' in it
        parts = name.split('_')
        engine, stream = parts[-2], parts[-1]
        workload = '_'.join(parts[:-2])
        cells[(workload, stream, engine)] = load_cell(rep)
    return cells


def tables(cells):
    rows, checks = [], []
    for (workload, stream, engine), cell in sorted(cells.items()):
        s = summarize(cell)
        t = s.get('times') if isinstance(s.get('times'), dict) else {}
        rows.append({
            'workload': workload, 'stream': stream, 'engine': engine,
            'completed': s.get('completed'), 'ended_by': s.get('ended_by'),
            'outcome': s.get('outcome'), 'refused': s.get('refused'),
            'changed': s.get('changed'), 'rechecked': s.get('rechecked'),
            'selectivity': s.get('selectivity'), 'precision': s.get('precision'),
            't_total_ms': {k: _ms(t.get('t_total_s'), k)
                           for k in ('median', 'p90', 'p99', 'max')},
            't_update_ms_median': _ms(t.get('t_update_s'), 'median'),
            't_recheck_ms_median': _ms(t.get('t_recheck_s'), 'median'),
            'rss_mb': s.get('rss_mb'),
        })
    groups = {}
    for (workload, stream, engine), cell in cells.items():
        groups.setdefault((workload, stream), []).append((engine, cell))
    for (workload, stream), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        members.sort(key=lambda m: _ENGINES.index(m[0]) if m[0] in _ENGINES else 9)
        result = compare([c for _e, c in members])
        checks.append({'workload': workload, 'stream': stream,
                       'engines': [e for e, _c in members],
                       'agree': result.get('agree'),
                       'batches_compared': result.get('batches_compared'),
                       'disagreeing_batches': result.get('disagreeing_batches'),
                       'refusals_diverge_at_batch': result.get('refusals_diverge_at_batch'),
                       'why': result.get('why')})
    return rows, checks


def markdown(rows, checks):
    out = ['| workload | stream | engine | completed | refused | changed | '
           're-checked | selectivity | precision | t_total median | p90 | p99 | '
           'max | t_update med | t_recheck med |',
           '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        t = r['t_total_ms']
        out.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['workload'], r['stream'], r['engine'], r['completed'], r['refused'],
            r['changed'], r['rechecked'], _ratio(r['selectivity']),
            _ratio(r['precision']), t['median'], t['p90'], t['p99'], t['max'],
            r['t_update_ms_median'], r['t_recheck_ms_median']))
    out += ['', '| workload | stream | engines | agree | batches compared | '
            'disagreeing | refusals diverge at |', '|---|---|---|---|---:|---:|---|']
    for c in checks:
        out.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            c['workload'], c['stream'], ', '.join(c['engines']), c['agree'],
            c['batches_compared'], c['disagreeing_batches'],
            c['refusals_diverge_at_batch'] if c['refusals_diverge_at_batch'] is not None
            else '-'))
    return '\n'.join(out) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('cells_dir')
    parser.add_argument('--json', default=None)
    parser.add_argument('--md', default=None)
    args = parser.parse_args(argv)
    rows, checks = tables(collect(args.cells_dir))
    if args.json:
        with open(args.json, 'w') as handle:
            json.dump({'cells': rows, 'cross_engine': checks}, handle,
                      indent=1, sort_keys=True)
    text = markdown(rows, checks)
    if args.md:
        with open(args.md, 'w') as handle:
            handle.write(text)
    print(text)
    return 0 if all(c['agree'] for c in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
