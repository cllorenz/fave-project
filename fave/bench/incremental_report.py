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

""" Statistics of incremental streams, generated from their raw records --
INCREMENTAL_PLAN.md §7, O4, O5.

Reads cell directories written by `bench/incremental_run.py` (plain or, after
`bench/incremental_cell.py`, gzip'd JSON lines) and derives, never stores:

* the completed prefix, "n of N", and what ended the stream (O4.2);
* quantiles -- median, p90, p99, max, never a mean alone -- of `t_total_s`,
  `t_update_s`, `t_recheck_s`, per op at batch 1, and over the first
  `--warmup` updates separately (O4.4);
* **selectivity** = checks re-checked / (batches x checks) and **precision** =
  checks whose verdict changed / checks re-checked, each as the ratio of the
  stream's sums, with the distribution of re-checked counts per batch (O5);
* RSS after the build, after the first and the last batch, and its maximum;
* the **break-even share** given `--break-even-s`: batches whose `t_total_s`
  exceeds the same engine's from-zero build + full check (O4.3).

An oracle run's timings are not reported (O3.1): its rows carry the oracle's
outcome and the counts, not times. With several cells of one configuration
(repetitions), each is summarised alone and the spread of each quantile across
them is given -- never a pooled mean (O4.4).

Usage (from fave/):

    python3 bench/incremental_report.py results/cell/rep01 [...] --out sum.json
"""

import argparse
import json
import os
import statistics
import sys
import zlib


def read_lines(path):
    """ The records of a JSON-lines file, `path` or `path.gz`.

    Tolerates exactly what a stopped run leaves: a last line cut off mid-write,
    and a gzip stream without its trailer. Anything else malformed raises. """
    if os.path.exists(path):
        with open(path, 'rb') as handle:
            data = handle.read()
    elif os.path.exists(path + '.gz'):
        with open(path + '.gz', 'rb') as handle:
            raw = handle.read()
        data = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
    else:
        return []
    lines = data.split(b'\n')
    out = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            if i == len(lines) - 1:
                break                       # cut off mid-write by a stop
            raise
    return out


def _json(path):
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return json.load(handle)


def load_cell(directory):
    return {
        'dir': directory,
        'head': _json(os.path.join(directory, 'head.json')),
        'end': _json(os.path.join(directory, 'end.json')),
        'cell': _json(os.path.join(directory, 'cell.json')),
        'stream': read_lines(os.path.join(directory, 'stream.jsonl')),
        'updates': read_lines(os.path.join(directory, 'updates.jsonl')),
        'oracle': read_lines(os.path.join(directory, 'oracle.jsonl')),
    }


def quantiles(values):
    """ median, p90, p99, max (nearest rank) of a list, or None. """
    if not values:
        return None
    ordered = sorted(values)

    def at(q):
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]
    return {'n': len(ordered), 'median': statistics.median(ordered),
            'p90': at(0.90), 'p99': at(0.99), 'max': ordered[-1]}


def _times(batches):
    return {
        't_total_s': quantiles([b['t_update_s'] + b['t_recheck_s'] for b in batches]),
        't_update_s': quantiles([b['t_update_s'] for b in batches]),
        't_recheck_s': quantiles([b['t_recheck_s'] for b in batches]),
    }


def ended_by(cell):
    """ What ended the stream: `completed`, `oracle_failed`, a declared limit
    (`limit_wall`, `limit_stall`, `limit_rss`, `memory_floor`), `interrupted`
    (not a result: re-run), `error`, or `running/unknown` with no end record. """
    measured = (cell['cell'] or {}).get('measured') or {}
    if measured.get('status') == 'deadline':
        return measured.get('deadline_stop') or 'limit_wall'
    if measured.get('status') == 'memory':
        return measured.get('memory_stop') or 'limit_rss'
    if measured.get('status') in ('interrupted', 'error') and not cell['end']:
        return measured['status']
    if cell['end']:
        return cell['end']['status']
    return 'running/unknown'


def summarize(cell, break_even_s=None, warmup=100):
    head, batches = cell['head'], cell['updates']
    if head is None:
        return {'dir': cell['dir'], 'ended_by': ended_by(cell),
                'note': 'no head.json: the build did not finish'}
    done = sum(b['n'] for b in batches)
    n_checks = head['checks']
    rechecked = sum(b['rechecked'] for b in batches)
    changed = sum(len(b['changed']) for b in batches)
    timed = head.get('oracle') is None
    out = {
        'dir': cell['dir'],
        'workload': head['workload'], 'engine': head['engine'],
        'stream': head['stream'], 'seed': head['seed'],
        'fraction': head['fraction'] if head['stream'] == 's2' else None,
        'batch': head['batch'], 'checks': n_checks, 'rules': head['rules'],
        'stream_sha256': head['stream_sha256'],
        'ended_by': ended_by(cell),
        'completed': '%d of %d' % (done, head['updates']),
        'completed_updates': done, 'stream_updates': head['updates'],
        'batches': len(batches),
        'rechecked': rechecked, 'changed': changed,
        'selectivity': (rechecked / (len(batches) * n_checks)
                        if batches and n_checks else None),
        'precision': changed / rechecked if rechecked else None,
        'rechecked_per_batch': quantiles([b['rechecked'] for b in batches]),
        'unknown_affected_batches': sum(1 for b in batches if b['affected'] is None),
        'rss_mb': {'after_build': head.get('rss_after_build_mb'),
                   'first_batch': batches[0]['rss_mb'] if batches else None,
                   'last_batch': batches[-1]['rss_mb'] if batches else None,
                   'max': max((b['rss_mb'] for b in batches), default=None)},
        'stamps': {k: (cell['cell'] or {}).get(k) for k in (
            'limit_class', 'limit_wall_s', 'limit_rss_mb', 'limit_update_s',
            'limit_tripped', 'repetition', 'repetitions')},
    }
    if cell['cell'] and 'outcome' in cell['cell']:
        out['outcome'] = cell['cell']['outcome']
    if not timed:
        records = cell['oracle']
        out['oracle'] = {
            'batches_sampled': len(records),
            'full_checkpoints': sum(1 for r in records if r.get('full')),
            'sample_mismatches': sum(len(r['sample_mismatch']) for r in records),
            'selective_vs_full': sum(len(r.get('selective_vs_full', ()))
                                     for r in records),
            'full_vs_zero': sum(len(r.get('full_vs_zero', ())) for r in records),
            'passed': ended_by(cell) == 'completed' and not any(
                r['sample_mismatch'] or r.get('selective_vs_full')
                or r.get('full_vs_zero') for r in records),
        }
        out['times'] = 'not reported: an oracle run (INCREMENTAL_PLAN.md O3.1)'
        return out
    out['times'] = _times(batches)
    out['times_first_%d' % warmup] = _times([b for b in batches if b['pos'] < warmup])
    if head['batch'] == 1:
        out['times_by_op'] = {
            op: _times([b for b in batches if b['ops'] == [op]])
            for op in ('insert', 'delete', 'link_down', 'link_up')
            if any(b['ops'] == [op] for b in batches)}
    if break_even_s:
        over = sum(1 for b in batches
                   if b['t_update_s'] + b['t_recheck_s'] > break_even_s)
        out['break_even'] = {'from_zero_s': break_even_s, 'batches_over': over,
                             'share': over / len(batches) if batches else None}
    return out


def _config(summary):
    """ What makes cells repetitions of one configuration. """
    return (summary['workload'], summary['engine'], summary['stream'],
            summary['seed'], summary['batch'], summary['stream_sha256'])


def spread(summaries):
    """ Per quantile of `t_total_s`, its minimum and maximum across
    repetitions of ONE configuration -- the spread, not a pooled mean. """
    keys = {_config(s) for s in summaries if 'times' in s}
    if len(keys) != 1:
        raise ValueError("repetitions of different configurations: %s" % sorted(keys))
    out = {}
    for q in ('median', 'p90', 'p99', 'max'):
        values = [s['times']['t_total_s'][q] for s in summaries
                  if isinstance(s.get('times'), dict) and s['times']['t_total_s']]
        if values:
            out[q] = {'min': min(values), 'max': max(values), 'n': len(values)}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('cells', nargs='+', help="cell directories")
    parser.add_argument('--break-even-s', type=float, default=None,
                        help="the engine's from-zero build + full check, seconds")
    parser.add_argument('--warmup', type=int, default=100)
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    summaries = [summarize(load_cell(d), args.break_even_s, args.warmup)
                 for d in args.cells]
    report = {'cells': summaries}
    groups = {}
    for summary in summaries:
        if isinstance(summary.get('times'), dict):
            groups.setdefault(_config(summary), []).append(summary)
    report['spread_t_total_s'] = [
        {'configuration': list(key), 'spread': spread(members)}
        for key, members in sorted(groups.items()) if len(members) > 1]
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        with open(args.out, 'w') as handle:
            handle.write(text + '\n')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
