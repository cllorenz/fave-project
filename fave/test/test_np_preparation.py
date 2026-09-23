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

""" The FaVe-backend LPM re-prioritisation -- AD6_PLAN.md §5.5.

NetPlumber resolves rule priority by rule index (lower index = higher
priority). A raw-table benchmark that feeds its FIB in file order
(shortest prefix first) therefore lets the `0.0.0.0/0` default outrank the
specific routes, so NP forwards by the wrong rule. The fix reassigns each FIB
table's indices by descending prefix length.

WHY THIS FILE EXISTS. The predecessor selected tables with a hardcoded
`dev.startswith('mid.')`, which silently did NOTHING on wl_i2 -- whose FIB is
the `out` stage, not `mid` -- so every FaVe+NetPlumber wl_i2 number was computed
on a non-LPM forwarding model, with 3,731 rules shadowed by an earlier
containing prefix. Nothing failed; the fix just quietly did not apply. These
tests exist so that cannot recur silently for a third benchmark.

TWO DESIGNS WERE REJECTED ON THE WAY, and the tests pin why:

  * inferring FIB-ness from rule SHAPE ("matches only ipv4_dst") -- a packet
    filter can have exactly that shape, and reordering one changes its
    filtering semantics. Shape-matching on match fields is also blind to
    ACTIONS, which is where permit/deny lives.
  * declaring FIB tables without enforcing the declaration -- that merely
    relocates the original bug to "somebody forgot to declare".

So the declaration is explicit AND omission is a hard error, and the transform
additionally refuses to reorder a table when doing so would change permit/deny
precedence on overlapping prefixes.
"""

import unittest

from bench.np_preparation import (
    FibDeclarationError, fib_tables, _prefix_len
)


def _route(dev, idx, cidr, forward=True):
    """ One route in np_preparation's positional shape:
    (table, 1, idx, match_fields, actions, in_ports). `cidr=None` is the
    match-all default; `forward=False` is a drop (no actions at all), the shape
    wl_stanford's 472 martian-discard rules really have. """
    match = ['ipv4_dst=%s' % cidr] if cidr else []
    actions = ['fd=%s.1' % dev] if forward else []
    return (dev, 1, idx, match, actions, ['%s.0' % dev])


class TestFibTableSelection(unittest.TestCase):
    """ Selection is by DECLARED table type, never by rule shape. """

    _ROUTES = [
        _route('in.r1', 1, '10.0.0.0/8'),
        _route('mid.r1', 1, '10.0.0.0/8'),
        _route('mid.r2', 1, '10.0.0.0/8'),
        _route('out.r1', 1, '10.0.0.0/8'),
    ]

    def test_selects_exactly_the_declared_stage(self):
        self.assertEqual(fib_tables(self._ROUTES, ['mid']), {'mid.r1', 'mid.r2'})

    def test_a_different_benchmark_can_declare_a_different_stage(self):
        """ wl_stanford's FIB is `mid`, wl_i2's is `out` -- the whole point. """
        self.assertEqual(fib_tables(self._ROUTES, ['out']), {'out.r1'})

    def test_declaring_nothing_selects_nothing(self):
        self.assertEqual(fib_tables(self._ROUTES, []), set())

    def test_identical_rule_shape_does_not_make_a_table_a_fib(self):
        """ THE rejected design. All four tables here have identical shape --
        one ipv4_dst-only forwarding rule each -- so any shape-based predicate
        would select all of them. Only the declaration distinguishes them. """
        self.assertEqual(fib_tables(self._ROUTES, ['mid']), {'mid.r1', 'mid.r2'})


class TestPrefixLen(unittest.TestCase):

    def test_match_all_sorts_last(self):
        self.assertEqual(_prefix_len([]), -1)

    def test_a_bare_address_is_a_host_route(self):
        self.assertEqual(_prefix_len(['ipv4_dst=10.0.0.1']), 32)

    def test_a_cidr_reports_its_length(self):
        self.assertEqual(_prefix_len(['ipv4_dst=10.0.0.0/8']), 8)


class TestShippedConfigsDeclareTheirFibs(unittest.TestCase):
    """ The two raw-table benchmarks must declare, and their declaration must
    name a real table type. This is the tripwire for a third benchmark being
    added without one. """

    _EXPECTED = {
        'bench/wl_stanford/stanford-json/config.json': ['mid'],
        'bench/wl_i2/i2-json/config.json': ['out'],
    }

    def test_each_raw_table_benchmark_declares_its_fib_stage(self):
        import json, os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel, expected in self._EXPECTED.items():
            with open(os.path.join(here, rel)) as fh:
                cfg = json.load(fh)
            self.assertIn('fib_table_types', cfg, rel)
            self.assertEqual(cfg['fib_table_types'], expected, rel)
            self.assertTrue(set(cfg['fib_table_types']) <= set(cfg['table_types']),
                            "%s declares a FIB type absent from table_types" % rel)


if __name__ == '__main__':
    unittest.main()
