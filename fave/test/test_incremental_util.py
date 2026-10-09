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

""" The engine-independent parts of util/incremental.py (INCREMENTAL_PLAN.md
M1): check rounds, the streams, and the oracle's withholding wrapper. Pure
Python; the end-to-end streams are test_incremental_netplumber.py. """

import unittest

from types import SimpleNamespace

from aggregator.abstract_engine import AbstractVerificationEngine, UpdateRefused
from util import incremental as inc


def _rules(n):
    return [(('d', 'd.1', i), SimpleNamespace(idx=i)) for i in range(n)]


class TestRounds(unittest.TestCase):

    def test_a_pair_occurs_once_per_round(self):
        checks = [inc.Check(line) for line in (
            's=source.a && EF p=probe.b && f=related:0',
            's=source.a && EF p=probe.b && f=related:1',
            's=source.c && EF p=probe.b',
        )]
        rounds = inc._rounds(checks)
        self.assertEqual([len(r) for r in rounds], [2, 1])
        for round_ in rounds:
            pairs = [c.pair for c in round_]
            self.assertEqual(len(pairs), len(set(pairs)))
        # every check is asked exactly once
        self.assertEqual(sorted(c.line for r in rounds for c in r),
                         sorted(c.line for c in checks))


class TestStreams(unittest.TestCase):

    def test_s1_deletes_in_reverse_then_inserts_in_order(self):
        stream = list(inc.stream_s1(_rules(3)))
        self.assertEqual([(op, key[2]) for op, key, _r in stream],
                         [('delete', 2), ('delete', 1), ('delete', 0),
                          ('insert', 0), ('insert', 1), ('insert', 2)])

    def test_s2_is_a_function_of_its_seed(self):
        rules = _rules(50)
        one = [(op, k) for op, k, _r in inc.stream_s2(rules, 0.2, seed=7)]
        two = [(op, k) for op, k, _r in inc.stream_s2(rules, 0.2, seed=7)]
        other = [(op, k) for op, k, _r in inc.stream_s2(rules, 0.2, seed=8)]
        self.assertEqual(one, two)
        self.assertNotEqual(one, other)
        self.assertEqual(len(one), 2 * 10)
        deleted = [k for op, k in one if op == 'delete']
        inserted = [k for op, k in one if op == 'insert']
        self.assertEqual(deleted, inserted)

    def test_s3_takes_each_link_down_then_up(self):
        stream = list(inc.stream_s3([('a.1', 'b.1'), ('b.2', 'c.1')]))
        self.assertEqual([op for op, _l, _r in stream],
                         ['link_down', 'link_up', 'link_down', 'link_up'])

    def test_apply_keeps_the_oracles_view_in_step(self):
        calls = []
        engine = SimpleNamespace(
            delete_rule=lambda *k: calls.append(('del', k)),
            insert_rule=lambda r: calls.append(('ins', r.idx)),
            set_link=lambda s, d, up: calls.append(('link', s, d, up)))
        deleted, down = set(), set()
        key, rule = _rules(1)[0]
        inc.apply(engine, ('delete', key, rule), deleted, down)
        self.assertEqual(deleted, {key})
        inc.apply(engine, ('insert', key, rule), deleted, down)
        self.assertEqual(deleted, set())
        inc.apply(engine, ('link_down', ('a', 'b'), None), deleted, down)
        self.assertEqual(down, {('a', 'b')})
        inc.apply(engine, ('link_up', ('a', 'b'), None), deleted, down)
        self.assertEqual(down, set())
        self.assertEqual(len(calls), 4)


class TestWithholding(unittest.TestCase):
    """ The oracle builds the CURRENT model from zero: rules deleted and links
    taken down so far never reach the fresh engine. """

    def test_deleted_rules_and_downed_links_are_withheld(self):
        seen = {'rules': {}, 'links': [], 'bulk': []}
        engine = SimpleNamespace(
            add_rules=lambda m: seen.__setitem__('rules', m.tables),
            add_link=lambda s, d: seen['links'].append((s, d)),
            add_links_bulk=lambda links, use_dynamic=False:
                seen.__setitem__('bulk', list(links)),
            links={})
        wrapped = inc._Withholding(engine, {('n', 'n.1', 1)}, {('a', 'b')})
        model = SimpleNamespace(node='n', tables={'n.1': [
            SimpleNamespace(idx=0), SimpleNamespace(idx=1)]})
        wrapped.add_rules(model)
        self.assertEqual([r.idx for r in seen['rules']['n.1']], [0])
        self.assertEqual([r.idx for r in model.tables['n.1']], [0, 1],
                         "the aggregator's model must not be edited")
        wrapped.add_link('a', 'b')
        wrapped.add_link('b', 'c')
        self.assertEqual(seen['links'], [('b', 'c')])
        wrapped.add_links_bulk([('a', 'b'), ('c', 'd')])
        self.assertEqual(seen['bulk'], [('c', 'd')])
        # attributes the aggregator mutates in place are the engine's own
        wrapped.links.setdefault(1, []).append(2)
        self.assertEqual(engine.links, {1: [2]})


class TestTheDefaultsAreSound(unittest.TestCase):

    def test_an_engine_without_updates_refuses_them_and_knows_nothing(self):
        engine = AbstractVerificationEngine()
        for update in (lambda: engine.insert_rule(SimpleNamespace(idx=0)),
                       lambda: engine.delete_rule('n', 'n.1', 0),
                       lambda: engine.set_link('a', 'b', False)):
            with self.assertRaises(UpdateRefused):
                update()
        engine.track_affected(True)
        self.assertIsNone(engine.take_affected(),
                          "unknown must mean: re-verify every check")


if __name__ == '__main__':
    unittest.main()
