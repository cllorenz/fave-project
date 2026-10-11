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

""" util/stable_index.py (INCREMENTAL_PLAN.md §8.1): stable indices by
alignment. Pure Python; the end-to-end use is in test_incremental_m2.py. """

import random
import unittest

from rule.rule_model import Forward, Match, Rule, RuleField
from util.stable_index import IndexBudgetExceeded, StableIndexer, diff, key


def _rule(i, port='1'):
    """ A distinct rule per i (by its match). """
    return Rule('n', 'n.t', i, in_ports=['n.in'],
                match=Match([RuleField('packet.upper.dport', str(i))]),
                actions=[Forward(['n.' + port])])


def _emit(ix, rules):
    return ix.emit('n', 'n.t', rules)


class TestStableIndexer(unittest.TestCase):

    def test_first_emission_is_spaced_and_ordered(self):
        ix = StableIndexer(lambda _t: 1000)
        out = _emit(ix, [_rule(i) for i in range(4)])
        self.assertEqual([r.idx for r in out], [100, 200, 300, 400])
        # copies: the generator's rules keep their own indices
        self.assertEqual([key(r) for r in out], [key(_rule(i)) for i in range(4)])

    def test_unchanged_rules_keep_their_index(self):
        ix = StableIndexer(lambda _t: 1000)
        rules = [_rule(i) for i in range(10)]
        first = {key(r): r.idx for r in _emit(ix, rules)}
        edited = rules[:3] + [_rule(99)] + rules[3:7] + rules[8:]   # insert, delete
        second = _emit(ix, edited)
        for r in second:
            if key(r) in first:
                self.assertEqual(r.idx, first[key(r)])
        self.assertEqual([key(r) for r in sorted(second, key=lambda r: r.idx)],
                         [key(r) for r in edited])

    def test_raw_line_metadata_is_not_content(self):
        a, b = _rule(1), _rule(1)
        a.raw_line_no, b.raw_line_no = 3, 4
        self.assertEqual(key(a), key(b))

    def test_the_diff_is_the_edit(self):
        ix = StableIndexer(lambda _t: 1000)
        rules = [_rule(i) for i in range(10)]
        _emit(ix, rules)
        prev = ix.last('n', 'n.t')
        edited = rules[:3] + [_rule(99)] + rules[3:7] + rules[8:]
        out = _emit(ix, edited)
        deletes, inserts = diff(prev, out)
        self.assertEqual(len(deletes), 1)
        self.assertEqual([key(r) for r in inserts], [key(_rule(99))])
        # a modify: same position, new content -> one delete, one insert
        prev = ix.last('n', 'n.t')
        modified = list(edited)
        modified[5] = _rule(5, port='2')
        deletes, inserts = diff(prev, _emit(ix, modified))
        self.assertEqual((len(deletes), len(inserts)), (1, 1))
        self.assertEqual(deletes[0], inserts[0].idx)

    def test_a_full_gap_relabels_a_window_not_the_table(self):
        ix = StableIndexer(lambda _t: 10_000)
        rules = [_rule(i) for i in range(100)]
        _emit(ix, rules)
        # 40 inserts at one spot: the gap (~50) runs out, windows relabel
        for n in range(40):
            rules.insert(50, _rule(1000 + n))
            prev = ix.last('n', 'n.t')
            out = _emit(ix, rules)
            self.assertEqual([key(r) for r in sorted(out, key=lambda r: r.idx)],
                             [key(r) for r in rules])
            deletes, inserts = diff(prev, out)
            # never the whole table
            self.assertLess(len(inserts), len(rules) // 2)
        self.assertGreater(ix.stats['windows'], 0)

    def test_random_edits_keep_order_and_budget(self):
        rnd = random.Random(7)
        ix = StableIndexer(lambda _t: 5_000)
        rules = [_rule(i) for i in range(200)]
        _emit(ix, rules)
        fresh = 10_000
        for _ in range(300):
            op = rnd.choice(['insert', 'delete', 'modify'])
            pos = rnd.randrange(len(rules))
            if op == 'insert':
                rules.insert(pos, _rule(fresh))
                fresh += 1
            elif op == 'delete' and len(rules) > 1:
                del rules[pos]
            else:
                rules[pos] = _rule(fresh)
                fresh += 1
            out = _emit(ix, rules)
            idxs = [r.idx for r in out]
            self.assertEqual(idxs, sorted(idxs))
            self.assertEqual(len(set(idxs)), len(idxs))
            self.assertTrue(1 <= idxs[0] and idxs[-1] <= 5_000)

    def test_a_table_larger_than_its_budget_is_refused(self):
        ix = StableIndexer(lambda _t: 10)
        with self.assertRaises(IndexBudgetExceeded):
            _emit(ix, [_rule(i) for i in range(11)])

    def test_tables_and_nodes_are_independent(self):
        ix = StableIndexer(lambda t: 1000 if t == 'n.t' else 100)
        a = ix.emit('n', 'n.t', [_rule(0)])
        b = ix.emit('n', 'n.u', [_rule(0)])
        self.assertEqual((a[0].idx, b[0].idx), (250, 25))   # budget / (2(n+1))
        ix.forget('n')
        self.assertIsNone(ix.last('n', 'n.t'))


if __name__ == '__main__':
    unittest.main()
