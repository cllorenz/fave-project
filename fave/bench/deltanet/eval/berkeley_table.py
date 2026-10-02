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

""" The table CLOUD_BENCH_PLAN.md §2.15 quotes for `wl_berkeley`'s size series,
re-derived from `berkeley_series.py`'s result files.

Refuses if any completed plain run is not a valid 0/520, if a mutated run is
not exactly 1 violation of 520 on the mutated cell, or if the runs of one size
did not all see the same inputs: a cost compared across runs that answered
different questions is not a comparison. The growth exponent between
consecutive sizes is log(cost ratio) / log(rule ratio) -- 1 is linear.

An exponent follows every cost that has one, the JVM's live heap included.
That column was added 2026-10-02: the live heap had been printed without it,
so the one measurement that sizes the engine's memory was the one a reader had
to do arithmetic on. It is worth having in the table because it is NOT 1 --
NDD's live set came out sublinear in rules on `wl_berkeley` (0.548 and 0.582
between three sizes), and an extrapolation that assumed linear overestimated
the next size by 72%.

TWO CAVEATS ON THAT COLUMN, because it invites an inference the number cannot
quite carry. `max_heap_after_gc_mb` is an UPPER ESTIMATE of the live set, not
the live set: it is the smallest heap occupancy a GC happened to leave behind,
so it depends on when G1 chose to collect and on how roomy `-Xmx` was. Rows at
different `--jvm-xmx` are therefore not strictly comparable, and an exponent
spanning two such rows carries that confound -- the 2026-10-02 series pairs a
k=10 run at 8g with k=3 and k=2 at 16g. Second, the exponent is not constant:
the 2026-09-29 drill, at a constant 8g throughout, gives 0.33 between 459k and
1.35M rules against 0.55-0.58 higher up, so it RISES with size and an
extrapolation from the top of a series is, if anything, an underestimate.

Usage:  python3 berkeley_table.py bench/deltanet/eval/results_berkeley_2026-09-29
"""

import glob
import json
import math
import os
import sys


def _exponent(small, large, key):
    if not (small.get(key) and large.get(key)):
        return ''
    return '%.2f' % (math.log(large[key] / small[key]) /
                     math.log(large['rules'] / small['rules']))


def main(argv):
    rows = []
    for path in sorted(glob.glob(os.path.join(argv[1], 'k*.json'))):
        with open(path) as handle:
            rows.append(json.load(handle))

    for row in rows:
        if row['status'] == 'skipped':
            continue
        if row.get('mutated'):
            if not (row['verdict_valid'] and row['violations'] == 1
                    and row['checks'] == 520 and row['mutated_cell_check']
                    and not row['mutated_cell_check'][0].startswith('!')):
                raise SystemExit('mutated run %s is not exactly 1 of 520'
                                 % row['when'])
        elif row['status'] == 'completed' and not (
                row['verdict_valid'] and row['violations'] == 0
                and row['checks'] == 520):
            raise SystemExit('plain run k=%s %s is not a valid 0/520'
                             % (row['keep_every'], row['engine']))

    plain = [r for r in rows if not r.get('mutated') and r['status'] != 'skipped']
    for k in sorted({r['keep_every'] for r in plain}):
        seen = {json.dumps(r['input_files'], sort_keys=True)
                for r in plain if r['keep_every'] == k and 'input_files' in r}
        if len(seen) > 1:
            raise SystemExit('k=%d: runs saw %d input sets' % (k, len(seen)))

    print('| engine | k | rules | status | rule load s | x | compliance s | x '
          '| aggregator MB | net_plumber MB | JVM heap after GC MB | x |')
    print('|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    for engine in ('netplumber', 'ndd', 'bdd'):
        series = sorted((r for r in plain if r['engine'] == engine),
                        key=lambda r: -r['keep_every'])
        previous = None
        for row in series:
            peak = row.get('peak_rss_by_process_mb', {})
            gc = row.get('gc') or {}
            cell = {'rules': row.get('census', {}).get('rules'),
                    'load': row.get('switch_command_s'),
                    'check': (row.get('check_compliance_s') or [None])[0],
                    # Absent for NetPlumber, which has no JVM; `_exponent`
                    # returns '' rather than dividing by it.
                    'heap': gc.get('max_heap_after_gc_mb')}
            print('| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
                engine, row['keep_every'],
                '{:,}'.format(cell['rules']) if cell['rules'] else '?',
                row['status'],
                '%.1f' % cell['load'] if cell['load'] else '--',
                _exponent(previous, cell, 'load') if previous else '',
                '%.2f' % cell['check'] if cell['check'] else '--',
                _exponent(previous, cell, 'check') if previous else '',
                peak.get('aggregator', '--'), peak.get('net_plumber', '--'),
                cell['heap'] if cell['heap'] else '--',
                # ONLY between two completed runs. A run the floor or the
                # deadline killed reports the heap it had reached when it died,
                # not a peak -- §2.15's 8g k=3 run showed 4.0 GB that way and
                # the live set was above 5.1. An exponent off a truncated
                # figure reads as slow growth and means nothing; the load and
                # compliance columns above print one regardless, which is
                # defensible for them (a run killed in the compliance check did
                # finish loading) and is not for this one.
                _exponent(previous, cell, 'heap')
                if previous and row['status'] == 'completed' else ''))
            if row['status'] == 'completed':
                previous = cell
    for row in rows:
        if row.get('mutated'):
            print('mutated %s k=%d: %d of %d -- %s' % (
                row['engine'], row['keep_every'], row['violations'],
                row['checks'], row['violation_lines']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
