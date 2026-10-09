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

""" The cross-engine check of incremental streams -- INCREMENTAL_PLAN.md O3.2.

Every measured stream is run incrementally on every engine that can, and each
update's set of changed checks must be the same on all of them: distinct check
lines, with their new verdicts. Before that, the cells must be comparable --
the same stream (by hash), the same check set, the same batching -- and must
agree on every check's initial verdict. A disagreement is a defect and voids
the stream's selective numbers until explained (O5); this exits 1 on one.

Cells stopped by a limit are compared over their common prefix, which is said.

Usage (from fave/):

    python3 bench/incremental_compare.py cells/np/rep01 cells/vf/rep01
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

# pylint: disable=wrong-import-position
from bench.incremental_report import load_cell

#: disagreements listed in full; the count is always complete
_SHOWN = 20


def compare(cells):
    heads = [c['head'] for c in cells]
    if any(h is None for h in heads):
        return {'comparable': False, 'why': 'a cell has no head.json'}
    for field in ('stream_sha256', 'checks_sha256', 'batch'):
        values = {h[field] for h in heads}
        if len(values) != 1:
            return {'comparable': False,
                    'why': 'cells differ in %s: %s' % (field, sorted(map(str, values)))}
    initial = [h['initial_verdicts'] for h in heads]
    differs = sorted(line for line in initial[0]
                     if any(v.get(line) != initial[0][line] for v in initial[1:]))
    common = min(len(c['updates']) for c in cells)
    # A refused update leaves that engine's model behind the others', so their
    # changes are comparable only up to the first batch the cells refused
    # differently -- and that is said, never compared past.
    diverged = None
    for b in range(common):
        refused = {tuple(pos for pos, _r in c['updates'][b].get('refused', ()))
                   for c in cells}
        if len(refused) != 1:
            diverged = b
            common = b
            break
    disagreements = []
    for b in range(common):
        sets = [frozenset((line, new) for line, _old, new in c['updates'][b]['changed'])
                for c in cells]
        if len(set(sets)) != 1:
            disagreements.append({
                'b': b, 'pos': cells[0]['updates'][b]['pos'],
                'changed': [[c['head']['engine'], sorted(map(list, s))]
                            for c, s in zip(cells, sets)]})
    return {
        'comparable': True,
        'engines': [h['engine'] for h in heads],
        'batches_compared': common,
        'refusals_diverge_at_batch': diverged,
        'batches_per_cell': [len(c['updates']) for c in cells],
        'initial_verdicts_differ': differs[:_SHOWN],
        'initial_verdicts_differ_count': len(differs),
        'disagreeing_batches': len(disagreements),
        'disagreements': disagreements[:_SHOWN],
        'agree': not differs and not disagreements and diverged is None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('cells', nargs='+', help="two or more cell directories")
    args = parser.parse_args(argv)
    if len(args.cells) < 2:
        parser.error("compare needs at least two cells")
    result = compare([load_cell(d) for d in args.cells])
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if result.get('agree') else 1


if __name__ == '__main__':
    sys.exit(main())
