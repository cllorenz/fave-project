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

""" The table CLOUD_BENCH_PLAN.md §2.13 quotes, re-derived from `engine_run.py`
result files -- every `*.json` under the directory given, recursively.

Refuses rather than summarises if any unmutated run is not a valid 0/256, or if
the runs of one trace did not all see byte-identical inputs: a median over runs
that answered different questions is not a figure.

Usage:  python3 summarize_runs.py bench/deltanet/eval/results_2026-09-29
"""

import glob
import json
import os
import statistics
import sys


def main(argv):
    rows = [json.load(open(path)) for path in sorted(glob.glob(
        os.path.join(argv[1], '**', '*.json'), recursive=True))]
    rows = [r for r in rows if r.get('status') != 'skipped']
    plain = [r for r in rows if not r['mutated']]
    bad = [r for r in plain
           if not (r['verdict_valid'] and r['violations'] == 0)]
    if bad:
        raise SystemExit("%d unmutated run(s) are not a valid zero" % len(bad))

    for workload in sorted({r['workload'] for r in plain}):
        inputs = {json.dumps(r['input_files'], sort_keys=True)
                  for r in plain if r['workload'] == workload}
        if len(inputs) != 1:
            raise SystemExit("%s: runs saw %d different input sets"
                             % (workload, len(inputs)))

    cells = {}
    for row in plain:
        cells.setdefault((row['workload'], row['engine']), []).append(
            row['check_compliance_s'][0])
    print("| trace | engine | n | median s | min-max s | checks |")
    print("|---|---|---:|---:|---|---:|")
    for (workload, engine), values in sorted(cells.items()):
        values.sort()
        print("| %s | %s | %d | %.2f | %.2f-%.2f | 256 |" % (
            workload, engine, len(values), statistics.median(values),
            values[0], values[-1]))
    for workload in sorted({w for w, _ in cells}):
        if (workload, 'bdd') in cells and (workload, 'ndd') in cells:
            print("%s: BDD/NDD median ratio %.2f" % (workload, statistics.median(
                cells[(workload, 'bdd')]) / statistics.median(
                    cells[(workload, 'ndd')])))
    for engine in ('bdd', 'ndd'):
        one = cells.get(('wl_airtel1', engine))
        two = cells.get(('wl_airtel2', engine))
        if one and two:
            share = sum(x > y for x in two for y in one) / (len(one) * len(two))
            print("%s: airtel2/airtel1 median ratio %.3f, P(airtel2 run > "
                  "airtel1 run) %.2f" % (engine, statistics.median(two) /
                                         statistics.median(one), share))
    for row in rows:
        if row['mutated']:
            print("mutated %s %s: %s of %d -- %s" % (
                row['workload'], row['engine'], row['violations'],
                row['checks'], row['violation_lines']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
