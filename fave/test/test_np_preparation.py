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
    FibDeclarationError, fib_tables, _reprioritise_fib_lpm, _prefix_len
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


class TestReprioritise(unittest.TestCase):

    def _idx(self, routes, dev):
        return [(r[2], r[3][0].split('=')[1] if r[3] else 'default')
                for r in routes if r[0] == dev]

    def test_longer_prefixes_get_the_lower_index(self):
        routes = [
            _route('mid.r', 1, None),            # default, file-order FIRST
            _route('mid.r', 2, '10.0.0.0/8'),
            _route('mid.r', 3, '10.1.0.0/16'),
        ]
        _reprioritise_fib_lpm(routes, ['mid'])
        self.assertEqual(self._idx(routes, 'mid.r'),
                         [(3, 'default'), (2, '10.0.0.0/8'), (1, '10.1.0.0/16')])

    def test_an_already_longest_first_table_is_unchanged(self):
        routes = [
            _route('mid.r', 1, '10.1.0.0/16'),
            _route('mid.r', 2, '10.0.0.0/8'),
            _route('mid.r', 3, None),
        ]
        before = list(routes)
        _reprioritise_fib_lpm(routes, ['mid'])
        self.assertEqual(routes, before, "no-op on an already-LPM table")

    def test_undeclared_tables_are_untouched(self):
        routes = [
            _route('in.r', 1, None),
            _route('in.r', 2, '10.1.0.0/16'),
        ]
        before = list(routes)
        _reprioritise_fib_lpm(routes, ['mid'])
        self.assertEqual(routes, before,
                         "an ACL stage must keep its file order -- reordering it "
                         "would change first-match permit/deny precedence")


class TestCrossClassPromotionsAreReportedNotRefused(unittest.TestCase):
    """ A declared FIB may hold drops as well as forwards. An earlier design
    REFUSED to reorder when doing so would swap an overlapping drop and
    forward, on the theory that this changes filtering semantics. The real
    wl_stanford data killed that theory: `mid.bbra_rtr` holds a `10.0.0.0/8`
    DROP ahead of a `10.240.0.0/12` FORWARD -- the standard FIB idiom of a
    discard aggregate with more-specific routes punched through it, which a
    real router resolves by longest prefix. Refusing it blocked the whole
    wl_stanford regeneration, whose LPM result is independently validated at
    165 pairs. In a FIB every rule participates in LPM, drops included, so the
    swap is always correct for a correctly-declared table -- and the shape is
    indistinguishable from a genuine deny-before-permit filter, so no automatic
    check can separate them. The DECLARATION is the contract; this is only
    reported. """

    def test_the_discard_aggregate_idiom_is_reordered_not_refused(self):
        routes = [
            _route('mid.r', 1, '10.0.0.0/8', forward=False),   # discard aggregate
            _route('mid.r', 2, '10.240.0.0/12'),               # punched through
        ]
        promotions = _reprioritise_fib_lpm(routes, ['mid'])
        got = {r[3][0].split('=')[1]: r[2] for r in routes}
        self.assertEqual(got, {'10.240.0.0/12': 1, '10.0.0.0/8': 2},
                         "longest prefix wins, exactly as a router resolves it")
        self.assertEqual(promotions, {'mid.r': 1}, "and the swap is REPORTED")

    def test_a_narrower_drop_promoted_past_a_broader_forward_is_not_reported(self):
        """ Raw wl_stanford also puts the `0.0.0.0/0` default BEFORE the
        `224.0.0.0/3` martian drop, making the drop dead code under
        first-match. LPM promotes the drop -- the correction this transform
        exists for -- and that is not a cross-class demotion of a forward. """
        routes = [
            _route('mid.r', 1, None),
            _route('mid.r', 2, '224.0.0.0/3', forward=False),
        ]
        promotions = _reprioritise_fib_lpm(routes, ['mid'])
        got = {(r[3][0].split('=')[1] if r[3] else 'default'): r[2] for r in routes}
        self.assertEqual(got, {'224.0.0.0/3': 1, 'default': 2})

    def test_a_table_with_no_drops_reports_nothing(self):
        routes = [_route('mid.r', 1, None), _route('mid.r', 2, '10.0.0.0/8')]
        self.assertEqual(_reprioritise_fib_lpm(routes, ['mid']), {})


class TestIdxIsAuthoritativeNotArrayPosition(unittest.TestCase):
    """ A table's rules are NOT stored in idx order, and `idx` is what
    NetPlumber resolves priority by. The precedence guard originally compared
    ARRAY POSITION instead, which made it refuse wl_stanford outright -- a
    table that is in fact already correctly ordered. These fixtures put array
    order and idx order deliberately at odds so that regression cannot pass
    unnoticed again. """

    def test_the_guard_reads_precedence_from_idx(self):
        """ By IDX the deny (idx 1) precedes the permit (idx 2), and LPM would
        flip them -> refuse. By ARRAY POSITION the permit comes first, which
        would (wrongly) look like no flip at all. """
        routes = [
            _route('mid.r', 2, '10.1.0.0/16'),                # permit, array-first
            _route('mid.r', 1, '10.0.0.0/8', forward=False),  # deny, idx-first
        ]
        promotions = _reprioritise_fib_lpm(routes, ['mid'])
        self.assertEqual(promotions, {'mid.r': 1},
                         "precedence is read from idx, so the swap is seen; by "
                         "ARRAY position the permit comes first and it would "
                         "look like no swap at all")

    def test_an_already_lpm_table_stored_out_of_idx_order_is_a_noop(self):
        """ The wl_stanford shape: correct by idx, shuffled in the array. Must
        reorder to exactly the indices it already has. """
        routes = [
            _route('mid.r', 3, None),                          # default, last by idx
            _route('mid.r', 1, '10.1.0.0/16', forward=False),  # drop, MOST specific
            _route('mid.r', 2, '10.0.0.0/8'),                  # forward it shadows
        ]
        _reprioritise_fib_lpm(routes, ['mid'])
        got = {(r[3][0].split('=')[1] if r[3] else 'default'): r[2] for r in routes}
        self.assertEqual(got, {'10.1.0.0/16': 1, '10.0.0.0/8': 2, 'default': 3})


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
