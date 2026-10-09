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

""" The campaign's matrix, built from the cells rather than typed.

`MEASUREMENT_RUN_PLAN.md` §9 says where results go and item 31 says what a cell
must carry, and between the two nothing ever read the cells back into a table.
Phase A's matrix was assembled by hand into `FINDINGS.md`, which is how a
`wl_cloud` row came to say "refuses (structural)" for a cell that answered.

WHAT IT REFUSES TO DO, because each is a way a comparison table misleads:

* **It will not merge two directories silently.** A cell re-measured after a fix
  lives in its own directory; `--over` names the later one explicitly and the
  table marks every overridden cell, so a reader sees that a row was replaced
  rather than discovering it in a git log.
* **It will not print a number without its outcome.** `0` from a cell that
  errored and `0` from a cell that answered are different facts, and
  `grep -c '^- '` on a missing report returns the first while looking like the
  second (`AD6_PLAN.md` §9.34.3).
* **It will not omit the denominator.** Every count is `violations/checks`.
  A workload with no check set prints `-`, not `0`.
* **It will not hide a limit trip.** `did_not_finish` carries which limit went
  and how far the cell got.

Usage (from fave/):

    python3 bench/campaigns/cell_table.py results_v5_20261002 \\
        --over results_v5_remeasure_20261006 --over results_v5_o1afix
"""

import argparse
import json
import os
import sys

#: Column order. Engines read left to right as the plan's §5.1 matrix does.
ENGINES = ('np', 'ndd', 'bdd', 'ad6', 'vf', 'vfplain')
ENGINE_LABEL = {'np': 'NetPlumber', 'ndd': 'NDD-flood', 'bdd': 'BDD-APKeep',
                'ad6': 'ad6', 'vf': 'VeriFlow-FR', 'vfplain': 'VF-plain'}

#: Cheapest first, as the queue runs them.
WORKLOADS = ('wl_example', 'wl_ifi', 'wl_cloud', 'wl_tum', 'wl_airtel1',
             'wl_airtel2', 'wl_stanford', 'wl_i2', 'wl_up')


#: How a cell's own stamps name the column it belongs in. The FILENAME
#: does not: `--out` is an operator's choice, and a cell measured under a
#: declared non-default encoding is worth naming for what it is
#: (`wl_i2_ad6_flow.json`) without thereby falling out of the table. Item
#: 31's rule is that provenance is STAMPED rather than typed, "so a table
#: cannot mislabel a row" -- and a table keyed on the filename is keyed on
#: a typed field.
def cell_key(cell, stem):
    """ The `<workload>_<engine>` key this cell belongs under, from its stamps.

    Falls back to the filename stem when the stamps cannot answer -- a
    result predating them, or a backend this table does not know. An
    unrecognised key simply matches no row, which is visible; filing a
    cell under the wrong column is not. """
    workload, backend = cell.get('workload'), cell.get('backend')
    if not workload or not backend:
        return stem
    if backend == 'netplumber':
        engine = 'np'
    elif backend == 'apkeep':
        engine = cell.get('engine')
    elif backend == 'ad6':
        engine = 'ad6'
    elif backend == 'veriflow':
        # The ablation is its own column, and `vf_fields` is the only thing
        # that separates them: both stamp `engine: veriflow`.
        engine = 'vf' if cell.get('vf_fields') == '4+10' else 'vfplain'
    else:
        return stem
    if engine not in ENGINES:
        return stem
    return '%s_%s' % (workload, engine)


def load(directories):
    """ key -> (cell, directory, filename stem). **The NEWEST cell wins, by its
    own `when` stamp** -- not by the order the directories were named.

    This was argument order once, and the first real table it produced was
    wrong: `--over remeasure --over o1afix` put the older `wl_tum` cells last,
    so two of them read `error` when the re-measure had already recorded them
    `measured`. A table whose correctness depends on the order of two flags is
    a table that will eventually be built with them the other way round.

    `when` is stamped by the cell itself (item 31), so this cannot be got wrong
    by the caller. A cell with no `when` sorts oldest, because an unstamped
    result predates the harness that stamps them.
    """
    found = {}
    for directory in directories:
        if not os.path.isdir(directory):
            raise SystemExit("no such directory: %s" % directory)
        for name in sorted(os.listdir(directory)):
            if not name.endswith('.json'):
                continue
            with open(os.path.join(directory, name)) as handle:
                cell = json.load(handle)
            stem = name[:-5]
            key = cell_key(cell, stem)
            when = cell.get('when') or ''
            if key in found and (found[key][0].get('when') or '') > when:
                continue
            found[key] = (cell, directory, stem)
    return found


def distinct_violations(directory, stem):
    """ How many DISTINCT checks the report names, against how many lines it
    prints. They differ on exactly one cell in the suite today.

    `cell_metrics.violations` counts report LINES. NetPlumber emits one line per
    witnessing header space, and HSA's union-of-wildcards representation is not
    canonical, so one violated check can be witnessed twice: `wl_cloud x np`
    reports `source.dc1_leaf6_host0 -> probe.dc0_leaf1_host1` under two
    OVERLAPPING dport fragments and scores 58 where every other engine scores
    57. That is a metric artefact and it read as a four-against-one engine
    disagreement until 2026-10-07.

    Returning None rather than guessing when the report is absent: a cell that
    produced no report has no numerator to count either way.
    """
    path = os.path.join(directory, stem + '.report.md')
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        section = handle.read().split('## Compliance Check', 1)[-1]
    section = section.split('\n## ', 1)[0]
    return len({l for l in section.splitlines() if l.startswith('- `')})


def verdict(cell):
    """ What the cell says, with its denominator and its outcome. """
    outcome = cell.get('outcome')
    checks, violations = cell.get('checks'), cell.get('violations')

    if outcome == 'did_not_finish':
        tripped = cell.get('limit_tripped')
        hours = (cell.get('wall_s') or 0) / 3600.0
        return 'DNF (%s, %.1f h)' % (tripped, hours)
    if outcome in ('error', 'interrupted'):
        # Never the count: a number from a cell that did not answer is the one
        # thing this table exists to stop being read as a result.
        return outcome
    if checks is None:
        # wl_tum: a throughput cell. `-` and not `0`, which would claim a
        # verdict it never reached.
        return '- (no checks)'
    return '%s/%s' % (violations, checks)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('base', help='the campaign directory')
    parser.add_argument('--over', action='append', default=[],
                        help='a later directory whose cells override the base; '
                             'repeatable, applied in order')
    parser.add_argument('--timing', action='store_true',
                        help='wall-clock and peak RSS instead of verdicts')
    args = parser.parse_args(argv)

    cells = load([args.base] + args.over)
    overridden = {key for key, (_c, d, _s) in cells.items() if d != args.base}
    duplicated = set()

    print('| workload | ' + ' | '.join(ENGINE_LABEL[e] for e in ENGINES) + ' |')
    print('|---|' + '---|' * len(ENGINES))
    for workload in WORKLOADS:
        row = [workload]
        for engine in ENGINES:
            stem = '%s_%s' % (workload, engine)
            if stem not in cells:
                row.append('—')
                continue
            cell, came_from, filed_as = cells[stem]
            if args.timing:
                text = '%.1f s / %s MB' % (cell.get('wall_s') or 0,
                                           cell.get('peak_rss_mb'))
            else:
                text = verdict(cell)
                # Flag, rather than silently correct, a cell whose report
                # prints more LINES than it names distinct checks. Changing the
                # metric would move recorded numbers across the campaign and is
                # the owner's call; hiding the discrepancy is not.
                n = distinct_violations(came_from, filed_as)
                if n is not None and cell.get('violations') not in (None, n):
                    text += ' ‡%d' % n
                    duplicated.add(stem)
            row.append(text + (' †' if stem in overridden else ''))
        print('| ' + ' | '.join(row) + ' |')

    if duplicated:
        print()
        print('‡ the report prints more LINES than it names distinct checks, so '
              'the count left of the ‡ is not comparable across engines; the '
              'number right of it is the distinct count. '
              '`cell_metrics.violations` counts lines.')
        for stem in sorted(duplicated):
            print('  - %s' % stem)

    if overridden:
        print()
        print('† the cell comes from a later directory than %s: re-measured '
              'after a fix, or measured under a declared encoding the base '
              'cell did not use. Each is named with the options that '
              'produced it.' % args.base)
        for stem in sorted(overridden):
            cell, came_from, filed_as = cells[stem]
            options = cell.get('engine_options') or ''
            print('  - %s (%s/%s.json%s)'
                  % (stem, came_from, filed_as,
                     ', `%s`' % options if options else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
