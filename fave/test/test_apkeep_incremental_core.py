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

""" The APKeep fork's update path on tiny networks, against a from-zero build
of the same rules (APKEEP_INCREMENTAL_SCOPE.md §2, step 1; INCREMENTAL_PLAN.md
O6): ties are resolved on removal as if the removed rule had never been
inserted, rule identity includes the match, links can be taken down and up,
and a query's footprint reports exactly the updates that meet it.

Each network here is small enough that a fresh one per test is cheap; the BDD
table is sized down accordingly, and `Network.activate` lets several live side
by side in the one JVM.
"""

import unittest

from apkeep.adapter import _filter_rule_string, _nat_ip_rule_string
from apkeep.lib_apkeep import LibAPKeep, available
from test.backend_gate import require_or_skip

#: src -> f, and f's ports a, b lead to dA, dB
_EDGES = ["src 1 f 1", "f a dA 1", "f b dB 1"]


def _filter(port, idx, dst=None):
    """ A first-match rule; the LOWER idx wins (priority = base - idx). """
    return _filter_rule_string('f', port, None, None, dst, None, None, None, idx)


def _fwd(port, prio, prefix='167772160', plen='8'):
    return "+ fwd f %s %s %s %d" % (prefix, plen, port, prio)


def _net(rules, filters=True):
    lib = LibAPKeep()
    lib.init_in_memory("t", _EDGES, None if filters else ['f'], None, None,
                       device_filters=['f'] if filters else None,
                       bdd_table_size=10_000)
    lib.run(rules)
    return lib


def _reach(lib):
    return (lib.is_reachable('src', '1', 'dA', '1'),
            lib.is_reachable('src', '1', 'dB', '1'))


def _minus(rule):
    return '- ' + rule[2:]


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestTiesOnRemoval(unittest.TestCase):
    """ Equal priority: the rule inserted LAST wins. Removing it must hand its
    packets to the tied rule it shadowed, as a build without it would --
    upstream skipped every equal-priority rule and gave them to a lower one. """

    def test_a_first_match_tie(self):
        a, b = _filter('a', 5), _filter('b', 5)
        both = _net([a, b])
        self.assertEqual(_reach(both), (False, True), "b, inserted last, wins")
        both.update([_minus(b)])
        self.assertEqual(_reach(both), _reach(_net([a])))
        self.assertEqual(_reach(both), (True, False))

    def test_removing_the_shadowed_one_changes_nothing(self):
        a, b = _filter('a', 5), _filter('b', 5)
        both = _net([a, b])
        both.update([_minus(a)])
        self.assertEqual(_reach(both), _reach(_net([b])))

    def test_a_forwarding_tie(self):
        a, b = _fwd('a', 8), _fwd('b', 8)
        both = _net([a, b], filters=False)
        self.assertEqual(_reach(both), (False, True))
        both.update([_minus(b)])
        self.assertEqual(_reach(both), _reach(_net([a], filters=False)))
        self.assertEqual(_reach(both), (True, False))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestNatPriorities(unittest.TestCase):
    """ O6: a NAT rule ranks as the first-match rule it rewrites for (its
    body's priority), not 65535 for all -- so of two overlapping rewrites on
    one port the table's winner wins, whatever the insertion order, and a
    removal leaves what a build without the rule would. """

    # src -> f -> (NAT on f.a) -> r, a router: 10/8 to dA, 20/8 to dB
    EDGES = ["src 1 f 1", "f a r 1", "r a dA 1", "r b dB 1"]

    def _net(self, nats):
        lib = LibAPKeep()
        lib.init_in_memory("t", self.EDGES, ['r'], None, {'f': ['a']},
                           device_filters=['f'], bdd_table_size=10_000)
        lib.run([_filter('a', 5),
                 "+ fwd r 167772160 8 a 8",      # 10.0.0.0/8
                 "+ fwd r 335544320 8 b 8"]      # 20.0.0.0/8
                + nats)
        return lib

    @staticmethod
    def _nat(idx, new):
        body = _filter_rule_string('f', 'a', None, None, None, None, None,
                                   None, idx).split(' ', 3)[3]
        return _nat_ip_rule_string('f', 'a', 'dst', new, body)

    def test_the_table_winner_rewrites(self):
        first, second = self._nat(1, '10.0.0.0/8'), self._nat(2, '20.0.0.0/8')
        for order in ([first, second], [second, first]):
            self.assertEqual(_reach(self._net(order)), (True, False), order)

    def test_a_removal_is_a_build_without_the_rule(self):
        first, second = self._nat(1, '10.0.0.0/8'), self._nat(2, '20.0.0.0/8')
        lib = self._net([first, second])
        lib.update([_minus(first)])
        self.assertEqual(_reach(lib), _reach(self._net([second])))
        self.assertEqual(_reach(lib), (False, True))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestIdentity(unittest.TestCase):

    def test_a_removal_takes_the_rule_with_its_match(self):
        # Same port, same priority, different matches: upstream's identity
        # (priority + port) let the removal of one take the other.
        narrow = _filter('a', 5, dst='10.0.0.0/8')
        wide = _filter('a', 5, dst='0.0.0.0/0')
        lib = _net([narrow, wide, _filter('b', 9)])
        lib.update([_minus(narrow)])
        # Upstream removed `wide` instead -- the first equal rule in the list
        # -- and left 10/8 to a and the rest to b: (True, True).
        self.assertEqual(_reach(lib), _reach(_net([wide, _filter('b', 9)])))
        self.assertEqual(_reach(lib), (True, False))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestLinks(unittest.TestCase):

    def test_down_and_up(self):
        lib = _net([_filter('a', 5)])
        self.assertEqual(_reach(lib), (True, False))
        lib.set_link('f', 'a', 'dA', '1', up=False)
        self.assertEqual(_reach(lib), (False, False))
        lib.set_link('f', 'a', 'dA', '1', up=True)
        self.assertEqual(_reach(lib), (True, False))

    def test_an_unknown_link_cannot_go_down(self):
        lib = _net([_filter('a', 5)])
        with self.assertRaises(Exception):
            lib.set_link('f', 'a', 'dB', '1', up=False)


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestFootprints(unittest.TestCase):
    """ A query's footprint is what ARRIVED at each element it visited; an
    update is reported iff its change meets that. """

    def _tracked(self):
        # 10/8 leaves by a, everything else by b
        lib = _net([_filter('a', 5, dst='10.0.0.0/8'), _filter('b', 9)])
        lib.track(True)
        lib.is_reachable('src', '1', 'dA', '1', footprint_key='to-a')
        return lib

    def test_a_change_inside_the_footprint_is_reported(self):
        lib = self._tracked()
        lib.update([_filter('b', 2, dst='10.1.0.0/16')])   # takes from a
        self.assertEqual(lib.take_affected(), ['to-a'])
        self.assertEqual(lib.take_affected(), [], "taken once")

    def test_the_footprint_is_what_arrived_not_what_left(self):
        lib = self._tracked()
        lib.update([_filter('a', 2, dst='192.168.0.0/16')])   # from b to a
        # Reported although the query's packets to dA were 10/8 only:
        # everything ARRIVED at f, so any change at f meets it. The
        # granularity is per element; an element the walk never reached stays
        # silent (below).
        self.assertEqual(lib.take_affected(), ['to-a'])

    def test_a_change_where_the_walk_never_arrived_is_not(self):
        lib = LibAPKeep()
        lib.init_in_memory("t", _EDGES + ["dB 1 g 1", "g c dC 1"], None, None,
                           None, device_filters=['f', 'g'], bdd_table_size=10_000)
        lib.run([_filter('a', 5)])               # nothing ever leaves by b
        lib.track(True)
        lib.is_reachable('src', '1', 'dA', '1', footprint_key='to-a')
        lib.update([_filter_rule_string('g', 'c', None, None, None, None, None,
                                        None, 1)])
        self.assertEqual(lib.take_affected(), [])

    def test_a_link_the_walk_used_is_reported(self):
        lib = self._tracked()
        lib.set_link('f', 'a', 'dA', '1', up=False)
        self.assertEqual(lib.take_affected(), ['to-a'])

    def test_a_link_the_walk_never_reached_is_not(self):
        lib = LibAPKeep()
        lib.init_in_memory("t", _EDGES + ["dB 1 x 1"], None, None, None,
                           device_filters=['f'], bdd_table_size=10_000)
        lib.run([_filter('a', 5)])
        lib.track(True)
        lib.is_reachable('src', '1', 'dA', '1', footprint_key='to-a')
        lib.set_link('dB', '1', 'x', '1', up=False)    # no packet reaches dB
        self.assertEqual(lib.take_affected(), [])

    def test_untracked_records_nothing(self):
        lib = _net([_filter('a', 5)])
        lib.is_reachable('src', '1', 'dA', '1', footprint_key='to-a')
        lib.track(True)
        lib.update([_filter('b', 9)])
        self.assertEqual(lib.take_affected(), [])


if __name__ == '__main__':
    unittest.main()
