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
#: `ndd` is NDD-APKeep and `nddflood` NDD-Flood since 2026-10-16 (owner); a
#: cell stamped with a bare `ndd` engine predates that and is NDD-Flood's.
ENGINES = ('np', 'ndd', 'nddflood', 'bdd', 'ad6', 'vf', 'vfplain')
ENGINE_LABEL = {'np': 'NetPlumber', 'ndd': 'NDD-APKeep', 'nddflood': 'NDD-Flood',
                'bdd': 'BDD-APKeep',
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
        # an unstamped cell predates the stamps, so an `_ndd` stem is NDD-Flood's
        return stem[:-4] + '_nddflood' if stem.endswith('_ndd') else stem
    if backend == 'netplumber':
        engine = 'np'
    elif backend == 'apkeep':
        # `cell_run.py` records the engine's own name; before 2026-10-16 it
        # recorded the option, whose `ndd` was NDD-Flood
        engine = {'ndd-apkeep': 'ndd', 'ndd-flood': 'nddflood',
                  'ndd': 'nddflood'}.get(cell.get('engine'), cell.get('engine'))
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


# --- the converged campaign (INCREMENTAL_PLAN.md D17) ---------------------------
#
# Its cells are `cells/<name>/repNN/cell.json` with the head of the shared
# initialization beside it (`head.json`). Every cell of every repetition --
# a stream cell or a from-zero-only one -- has measured the workload from
# zero once, so each is one SAMPLE of its (workload, engine); a stream cell
# stopped later by the cap still has its complete head.

#: the harness's engine names -> this table's columns
CONVERGED_ENGINE = {'netplumber': 'np', 'veriflow': 'vf', 'apkeep': 'bdd',
                    'ndd-apkeep': 'ndd', 'ad6': 'ad6'}
#: the phases of the from-zero measurement (D17.3)
PHASES = ('t_load_s', 't_build_s', 't_check_s')


def workload_name(path):
    """ `bench/wl_stanford/stanford-json` -> `wl_stanford`;
    `.../inputs/wl_berkeley_k30` -> `wl_berkeley_k30`. """
    parts = [p for p in os.path.normpath(path).split(os.sep) if p.startswith('wl_')]
    return parts[-1] if parts else os.path.basename(path)


def load_converged(directory):
    """ (workload, column) -> [sample], a sample being the cell record with
    its head (`head`; None when the cell stopped before its first check). """
    root = os.path.join(directory, 'cells')
    if not os.path.isdir(root):
        raise SystemExit("no cells/ in %s" % directory)
    found = {}
    for name in sorted(os.listdir(root)):
        cell_dir = os.path.join(root, name)
        if not os.path.isdir(cell_dir):
            continue
        for rep in sorted(os.listdir(cell_dir)):
            path = os.path.join(cell_dir, rep, 'cell.json')
            if not rep.startswith('rep') or not os.path.exists(path):
                continue
            with open(path) as handle:
                cell = json.load(handle)
            head_path = os.path.join(cell_dir, rep, 'head.json')
            head = None
            if os.path.exists(head_path):
                with open(head_path) as handle:
                    head = json.load(handle)
            cell = dict(cell, name=name, rep=rep, head=head)
            source = head or cell
            argv = cell.get('argv') or []
            workload = source.get('workload') or (argv[1] if len(argv) > 1 else None)
            engine = source.get('engine') or (
                argv[argv.index('--engine') + 1] if '--engine' in argv else None)
            if workload is None or engine not in CONVERGED_ENGINE:
                raise SystemExit("%s/%s: no workload or engine stamped" % (name, rep))
            key = (workload_name(workload), CONVERGED_ENGINE[engine])
            found.setdefault(key, []).append(cell)
    return found


def _stop(cell):
    """ How a cell with no from-zero verdict ended, never as a count. """
    outcome = cell.get('outcome')
    recorded = ' (recorded)' if cell.get('recorded') else ''
    tripped = cell.get('limit_tripped') or (cell.get('measured') or {}).get('limit_tripped')
    if outcome == 'did_not_finish':
        return ('timeout' if tripped == 'wall' else 'memory stop'
                if tripped == 'rss' else 'DNF (%s)' % tripped) + recorded
    if outcome == 'machine_stop':
        return 'machine stop'
    return outcome or 'no result'


def converged_verdict(samples):
    """ The from-zero verdict of a (workload, engine): distinct violated
    checks over checks, from every sample's head (D17.6). Samples that
    disagree are printed as such, never resolved; a pair without a head
    prints how its cells stopped. """
    heads = [c['head'] for c in samples if c.get('head') and c['head'].get('verdict_valid')]
    if not heads:
        stops = sorted({_stop(c) for c in samples})
        return ' / '.join(stops)
    counts = sorted({(h['violations'], h['checks']) for h in heads})
    verdicts = {json.dumps(h.get('initial_verdicts'), sort_keys=True) for h in heads}
    if len(counts) > 1 or len(verdicts) > 1:
        return 'DISAGREE ' + ', '.join('%s/%s' % c for c in counts)
    return '%s/%s (n=%d)' % (counts[0][0], counts[0][1], len(heads))


def _median(values):
    values = sorted(values)
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2.0


def converged_timing(samples):
    """ Median over the samples, with the range, per phase of the from-zero
    measurement; and the peak RSS and live heap of build and check. """
    heads = [c['head'] for c in samples if c.get('head') and c['head'].get('verdict_valid')]
    if not heads:
        return converged_verdict(samples)
    parts = []
    for phase in PHASES:
        values = [h['phases'][phase] for h in heads if phase in h.get('phases', {})]
        if values:
            parts.append('%s %.3g s [%.3g-%.3g]' % (phase[2:-2], _median(values),
                                                     min(values), max(values)))
    mem = [h.get('phase_memory', {}) for h in heads]
    peaks = [max(m.get(p, {}).get('peak_mb') or 0 for p in ('t_build_s', 't_check_s'))
             for m in mem]
    heaps = [m.get('t_check_s', {}).get('live_heap_mb') for m in mem]
    text = ', '.join(parts) + '; peak %.0f MB' % max(peaks)
    if any(h is not None for h in heaps):
        text += ', live heap %.0f MB' % max(h for h in heaps if h is not None)
    return text + ' (n=%d)' % len(heads)


def agreement(cells):
    """ Per workload: do the engines' initial verdicts agree check by check? """
    out = {}
    for (workload, engine), samples in cells.items():
        for c in samples:
            head = c.get('head')
            if head and head.get('verdict_valid'):
                out.setdefault(workload, {})[engine] = head.get('initial_verdicts') or {}
                break
    lines = []
    for workload in sorted(out):
        engines = out[workload]
        lines_differ = set()
        reference = next(iter(engines.values()))
        for verdicts in engines.values():
            lines_differ |= {l for l in set(reference) | set(verdicts)
                             if reference.get(l) != verdicts.get(l)}
        lines.append('| %s | %s | %s |' % (
            workload, ', '.join(ENGINE_LABEL[e] for e in sorted(engines)),
            'agree on all %d checks' % len(reference) if not lines_differ
            else '**%d checks differ**' % len(lines_differ)))
    return lines


def main_converged(args):
    cells = load_converged(args.base)
    if args.agreement:
        print('| workload | engines | initial verdicts |')
        print('|---|---|---|')
        for line in agreement(cells):
            print(line)
        return 0
    workloads = sorted({w for w, _e in cells})
    engines = [e for e in ENGINES if any(e == k[1] for k in cells)]
    print('| workload | ' + ' | '.join(ENGINE_LABEL[e] for e in engines) + ' |')
    print('|---|' + '---|' * len(engines))
    for workload in workloads:
        row = [workload]
        for engine in engines:
            samples = cells.get((workload, engine))
            if not samples:
                row.append('—')
            else:
                row.append(converged_timing(samples) if args.timing
                           else converged_verdict(samples))
        print('| ' + ' | '.join(row) + ' |')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('base', help='the campaign directory')
    parser.add_argument('--over', action='append', default=[],
                        help='a later directory whose cells override the base; '
                             'repeatable, applied in order')
    parser.add_argument('--timing', action='store_true',
                        help='wall-clock and peak RSS instead of verdicts')
    parser.add_argument('--agreement', action='store_true',
                        help='converged campaign: do the engines agree per check')
    args = parser.parse_args(argv)
    if os.path.isdir(os.path.join(args.base, 'cells')):
        # the converged campaign (D17): one directory, repetitions as samples
        if args.over:
            parser.error("--over is for V5's directories; a converged campaign "
                         "is one directory")
        return main_converged(args)

    cells = load([args.base] + args.over)
    overridden = {key for key, (_c, d, _s) in cells.items() if d != args.base}
    duplicated = set()

    # The engines measured: a column no cell is filed under is left out, so a
    # campaign from before an engine existed (V5 before NDD-APKeep) prints the
    # matrix it measured. Every cell of a printed column still shows `—` when
    # it is missing.
    engines = [e for e in ENGINES
               if any(key.endswith('_' + e) and key[:-len(e) - 1] in WORKLOADS
                      for key in cells)] or list(ENGINES)
    print('| workload | ' + ' | '.join(ENGINE_LABEL[e] for e in engines) + ' |')
    print('|---|' + '---|' * len(engines))
    for workload in WORKLOADS:
        row = [workload]
        for engine in engines:
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
