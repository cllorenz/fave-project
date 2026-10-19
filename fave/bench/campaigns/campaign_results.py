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

""" A converged campaign's RESULTS.md, generated from its cells and never
typed (INCREMENTAL_PLAN.md D17.11).

    python3 bench/campaigns/campaign_results.py <campaign dir>
        [--bridge <dir of V5-layout cells>] [--contention <dir of serial cells>]

Sections: the from-zero verdict matrix, the engines' agreement, the
from-zero cost per phase (`cell_table.py`'s converged mode); the bridge
(in-process against V5's live layout); the stream cells -- per configuration
the spread of `t_total` quantiles over the repetitions (never pooled), the
first 100 updates apart, selectivity and precision, the break-even share
against the SAME campaign's from-zero median, the footprint pass, and the
prefix of a stopped stream; the contention factor per engine. Run from fave/.
"""

import argparse
import contextlib
import io
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from bench import incremental_report as report  # noqa: E402
from bench.campaigns import cell_table  # noqa: E402

FROM_ZERO = ('t_load_s', 't_build_s', 't_check_s')


def _section(title: str, flags: List[str], base: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cell_table.main([base] + flags)
    return '## %s\n\n%s\n' % (title, buf.getvalue())


def from_zero_medians(cells: Dict[Tuple[str, str], List[Dict[str, Any]]]) -> Dict[Tuple[str, str], float]:
    """ (workload, column) -> median build + first check over its samples:
    the break-even share's denominator (O4.3, now the campaign's own). """
    out = {}
    for key, samples in cells.items():
        totals = [sum(c['head']['phases'].get(p, 0) for p in FROM_ZERO)
                  for c in samples if c.get('head') and c['head'].get('verdict_valid')]
        if totals:
            out[key] = cell_table._median(totals)   # pylint: disable=protected-access
    return out


def stream_rows(base: str, zero: Dict[Tuple[str, str], float]) -> List[str]:
    """ One row per configuration: the repetitions' spread, never a mean. """
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    footprint: Dict[Tuple[Any, ...], List[float]] = {}
    root = os.path.join(base, 'cells')
    for name in sorted(os.listdir(root)):
        for rep in sorted(os.listdir(os.path.join(root, name))):
            rep_dir = os.path.join(root, name, rep)
            if not rep.startswith('rep') or not os.path.isdir(rep_dir):
                continue
            cell = report.load_cell(rep_dir)
            head = cell['head']
            if head is None or head.get('stream') == 'z' or not head.get('updates'):
                continue
            key = (cell_table.workload_name(head['workload']),
                   cell_table.CONVERGED_ENGINE.get(head['engine'], head['engine']),
                   head['stream'], head['batch'], ','.join(head.get('footprint') or []) or '-',
                   head.get('seed'))
            s = report.summarize(cell, break_even_s=zero.get(key[:2]))
            groups.setdefault(key, []).append(s)
            if 't_footprint_s' in head.get('phases', {}):
                footprint.setdefault(key, []).append(head['phases']['t_footprint_s'])
    rows = ['| workload | engine | stream | batch | footprint | seed | reps | completed | '
            't_total median ms [min-max over reps] | first 100: median ms | selectivity | '
            'precision | break-even share | footprint pass s |',
            '|' + '---|' * 14]
    for key in sorted(groups, key=str):
        summaries = groups[key]
        timed = [s for s in summaries if isinstance(s.get('times'), dict)
                 and s['times'].get('t_total_s')]
        med = [s['times']['t_total_s']['median'] * 1000 for s in timed]
        first = [s['times_first_100']['t_total_s']['median'] * 1000 for s in timed
                 if s.get('times_first_100', {}).get('t_total_s')]
        share = [s['break_even']['share'] for s in timed if s.get('break_even')
                 and s['break_even'].get('share') is not None]
        sel = [s['selectivity'] for s in summaries if s.get('selectivity') is not None]
        prec = [s['precision'] for s in summaries if s.get('precision') is not None]
        span = lambda xs, f: ('%s [%s-%s]' % (f % cell_table._median(xs), f % min(xs), f % max(xs))  # noqa: E731
                              if xs else '—')
        completed = sorted({s.get('completed') or s.get('ended_by') for s in summaries})
        rows.append('| %s | %s | %s | %s | %s | %s | %d | %s | %s | %s | %s | %s | %s | %s |' % (
            key[0], cell_table.ENGINE_LABEL.get(key[1], key[1]), key[2], key[3], key[4], key[5],
            len(summaries), ', '.join(str(c) for c in completed),
            span(med, '%.3g'), span(first, '%.3g'), span(sel, '%.3g'), span(prec, '%.3g'),
            span(share, '%.3g'), span(footprint.get(key, []), '%.3g')))
    return rows


def bridge_rows(bridge_dir: str, zero: Dict[Tuple[str, str], float]) -> List[str]:
    """ V5's live layout against the in-process from-zero median (D17.4). """
    rows = ['| workload | engine | in-process build + check s | live layout: switch_command_s + '
            'check_compliance_s | wall s | ratio |', '|---|---|---|---|---|---|']
    for (cell, _d, _stem) in sorted(cell_table.load([bridge_dir]).values(),
                                    key=lambda t: t[2]):
        workload = cell.get('workload')
        column = cell_table.cell_key(cell, '').rsplit('_', 1)[-1]
        inproc = zero.get((workload, column))
        live = (cell.get('switch_command_s') or 0) + sum(cell.get('check_compliance_s') or [])
        rows.append('| %s | %s | %s | %.3g | %.3g | %s |' % (
            workload, cell_table.ENGINE_LABEL.get(column, column),
            '%.3g' % inproc if inproc else '—', live, cell.get('wall_s') or 0,
            '%.2f' % (live / inproc) if inproc and live else '—'))
    return rows


#: why a V5 number is not this campaign's on the same pair (D17.10, D17.1)
V5_NOT_COMPARABLE = {
    'wl_tum': "V5 ran it without checks and before the port-range fix",
}
V5_CAVEAT = {
    'bdd': "APKeep's structure is per ingress port without elision since 2026-10-19 (V5: classes, elision)",
    'ndd': "NDD-APKeep did not exist in V5",
}


def v5_rows(v5_dirs: List[str], zero: Dict[Tuple[str, str], float]) -> List[str]:
    """ V5's from-zero time beside the campaign's, where the model is the
    same; every exception stated, none hidden (D17.11). V5's number is its
    live layout's switch_command_s + check_compliance_s (the build and the
    check, without input generation and start-up). """
    v5 = cell_table.load(v5_dirs)
    rows = ['| workload | engine | V5 s | campaign s | note |', '|---|---|---|---|---|']
    for (workload, column), value in sorted(zero.items()):
        cell = (v5.get('%s_%s' % (workload, column)) or (None,))[0]
        note = V5_NOT_COMPARABLE.get(workload) or V5_CAVEAT.get(column, '')
        if cell is None:
            rows.append('| %s | %s | — | %.3g | not in V5 |' % (
                workload, cell_table.ENGINE_LABEL.get(column, column), value))
            continue
        v5_s = (cell.get('switch_command_s') or 0) + sum(cell.get('check_compliance_s') or [])
        shown = ('%.3g' % v5_s if cell.get('outcome') not in ('did_not_finish', 'error')
                 else cell_table.verdict(cell))
        rows.append('| %s | %s | %s | %.3g | %s |' % (
            workload, cell_table.ENGINE_LABEL.get(column, column),
            shown if workload not in V5_NOT_COMPARABLE else 'not comparable', value, note))
    return rows


def contention_rows(base_zero: Dict[Tuple[str, str], float], serial_dir: str) -> List[str]:
    """ Per engine: the parallel cells' from-zero median over the serial
    sample's (D17.8). """
    serial = from_zero_medians(cell_table.load_converged(serial_dir))
    ratios: Dict[str, List[float]] = {}
    for key, value in serial.items():
        if key in base_zero and value:
            ratios.setdefault(key[1], []).append(base_zero[key] / value)
    rows = ['| engine | pairs | contention factor, median [min-max] |', '|---|---|---|']
    for engine in sorted(ratios):
        xs = ratios[engine]
        rows.append('| %s | %d | %.3g [%.3g-%.3g] |' % (
            cell_table.ENGINE_LABEL.get(engine, engine), len(xs),
            cell_table._median(xs), min(xs), max(xs)))   # pylint: disable=protected-access
    return rows


def results(base: str, bridge: Optional[str] = None, contention: Optional[str] = None,
            v5: Optional[List[str]] = None) -> str:
    cells = cell_table.load_converged(base)
    zero = from_zero_medians(cells)
    parts = ['# Results -- generated by `bench/campaigns/campaign_results.py`, never typed\n',
             _section('1. From zero: verdicts (distinct violated / checks, n = samples)', [], base),
             _section('2. The engines\' agreement on the initial verdicts', ['--agreement'], base),
             _section('3. From zero: cost per phase (median [range] over samples)', ['--timing'], base)]
    if bridge:
        parts.append('## 4. Bridge: in-process against V5\'s live layout\n\n'
                     + '\n'.join(bridge_rows(bridge, zero)) + '\n')
    if v5:
        parts.append('## 4b. From zero against V5\n\n'
                     'Not the same span: V5\'s log sums its route commands and its checks '
                     '(`switch_command_s` + `check_compliance_s`, live layout); the campaign\'s '
                     'value is load + build + check of the whole model, in-process. The bridge '
                     '(section 4) measures both on the same inputs.\n\n'
                     + '\n'.join(v5_rows(v5, zero)) + '\n')
    parts.append('## 5. The streams\n\n' + '\n'.join(stream_rows(base, zero)) + '\n')
    if contention:
        parts.append('## 6. Contention: parallel over serial, per engine\n\n'
                     + '\n'.join(contention_rows(zero, contention)) + '\n')
    return '\n'.join(parts)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('base')
    parser.add_argument('--bridge')
    parser.add_argument('--contention')
    parser.add_argument('--v5', action='append', default=[],
                        help="a V5 result directory (repeatable; the newest cell wins, "
                             "as in cell_table.py)")
    parser.add_argument('--out', help="default: <base>/RESULTS.md")
    args = parser.parse_args(argv)
    text = results(args.base, args.bridge, args.contention, args.v5 or None)
    with open(args.out or os.path.join(args.base, 'RESULTS.md'), 'w') as out:
        out.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
