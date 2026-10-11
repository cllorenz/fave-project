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

import os
import unittest

from apkeep.adapter import _filter_rule_string, _nat_ip_rule_string
from apkeep.lib_apkeep import _NDD_JAR, LibAPKeep, available
from test.backend_gate import require_or_skip

#: src -> f, and f's ports a, b lead to dA, dB
_EDGES = ["src 1 f 1", "f a dA 1", "f b dB 1"]


def _filter(port, idx, dst=None):
    """ A first-match rule; the LOWER idx wins (priority = base - idx). """
    return _filter_rule_string('f', port, None, None, dst, None, None, None, idx)


def _fwd(port, prio, prefix='167772160', plen='8'):
    return "+ fwd f %s %s %s %d" % (prefix, plen, port, prio)


def _net(rules, filters=True):
    # the coarse footprint of APKEEP_INCREMENTAL_SCOPE.md §4, which
    # TestFootprints pins down; the default modes are tested below
    lib = LibAPKeep(footprint=())
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
        lib = LibAPKeep(footprint=())
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
        lib = LibAPKeep(footprint=())
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



# --- the selectable footprints (APKEEP_INCREMENTAL_SCOPE.md §9) ---------------

_ndd_available = available() and os.path.isfile(_NDD_JAR)


def _tracked_net(backend, footprint, edges, rules, nats=None, routers=None):
    lib = LibAPKeep(backend=backend, footprint=footprint)
    lib.init_in_memory("t", edges, routers, None, nats,
                       device_filters=['f'], bdd_table_size=10_000)
    lib.run(rules)
    lib.track(True)
    return lib


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestWitnessFootprints(unittest.TestCase):
    """ 'witness': a reachable query depends only on its witness path and,
    after the path's last rewrite, one packet of what arrived. """

    backend = 'bdd'
    # 10/8 leaves f by a (to dA), everything else by b (to dB)
    RULES = [_filter('a', 5, dst='10.0.0.0/8'), _filter('b', 9)]

    def _to_a(self, footprint=('witness',)):
        lib = _tracked_net(self.backend, footprint, _EDGES, self.RULES)
        self.assertTrue(lib.is_reachable('src', '1', 'dA', '1', footprint_key='to-a'))
        return lib

    def test_packets_moved_into_the_path_are_not_reported(self):
        update = [_filter('a', 2, dst='192.168.0.0/16')]     # from b to a
        default = self._to_a(())
        default.update(update)
        self.assertEqual(default.take_affected(), ['to-a'], "the default reports it")
        lib = self._to_a()
        lib.update(update)
        self.assertEqual(lib.take_affected(), [])

    def test_moving_the_whole_path_away_is_reported(self):
        lib = self._to_a()
        lib.update([_filter('b', 2, dst='10.0.0.0/8')])        # all of 10/8 to b
        self.assertEqual(lib.take_affected(), ['to-a'])
        self.assertFalse(lib.is_reachable('src', '1', 'dA', '1'))

    def test_only_the_half_holding_the_witness_packet_is_reported(self):
        # Moving either half of 10/8 off the path leaves the check reachable
        # through the other; only the half the witness packet is in is reported.
        # Which half that is depends on the packet picked, so count.
        reported = 0
        for half in ('10.0.0.0/9', '10.128.0.0/9'):
            lib = self._to_a()
            lib.update([_filter('b', 2, dst=half)])
            reported += len(lib.take_affected())
            self.assertTrue(lib.is_reachable('src', '1', 'dA', '1'), half)
        self.assertEqual(reported, 1)

    def test_a_link_on_the_path_is_reported(self):
        lib = self._to_a()
        lib.set_link('f', 'a', 'dA', '1', up=False)
        self.assertEqual(lib.take_affected(), ['to-a'])

    def test_an_unreachable_query_keeps_its_explored_footprint(self):
        lib = _tracked_net(self.backend, ('witness',), _EDGES, [_filter('a', 5)])
        self.assertFalse(lib.is_reachable('src', '1', 'dB', '1', footprint_key='to-b'))
        lib.update([_filter('b', 2, dst='192.168.0.0/16')])    # opens the path
        self.assertEqual(lib.take_affected(), ['to-b'])

    def test_before_a_rewrite_the_hop_keeps_what_arrived(self):
        # src -> f -> (NAT on f.a: dst := 10/8) -> r: 10/8 to dA, 20/8 to dB.
        # At r, after the rewrite, one packet stands for the path; at f, before
        # it, the arriving set does -- so either half moved off f.a is reported.
        edges = ["src 1 f 1", "f a r 1", "r a dA 1", "r b dB 1"]
        nat = _nat_ip_rule_string('f', 'a', 'dst', '10.0.0.0/8', _filter_rule_string(
            'f', 'a', None, None, None, None, None, None, 1).split(' ', 3)[3])
        rules = [_filter('a', 5), "+ fwd r 167772160 8 a 8", "+ fwd r 335544320 8 b 8", nat]
        at_f = at_r = 0
        for half in ('10.0.0.0/9', '10.128.0.0/9'):
            lib = _tracked_net(self.backend, ('witness',), edges, rules,
                               nats={'f': ['a']}, routers=['r'])
            self.assertTrue(lib.is_reachable('src', '1', 'dA', '1', footprint_key='k'))
            lib.update([_filter('b', 2, dst=half)])
            at_f += len(lib.take_affected())
            lib = _tracked_net(self.backend, ('witness',), edges, rules,
                               nats={'f': ['a']}, routers=['r'])
            self.assertTrue(lib.is_reachable('src', '1', 'dA', '1', footprint_key='k'))
            prefix, plen = half.split('/')
            ip = sum(int(o) << (24 - 8 * i) for i, o in enumerate(prefix.split('.')))
            lib.update(["+ fwd r %d %s b 9" % (ip, plen)])
            at_r += len(lib.take_affected())
        self.assertEqual((at_f, at_r), (2, 1))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestDeadEndFootprints(unittest.TestCase):
    """ 'dead-ends': an unreachable query ignores changes that only move
    packets into a dead end, and watches that port for a link coming up. """

    backend = 'bdd'
    # 10/8 to a (dA); the rest drops; nothing reaches dB
    RULES = [_filter('a', 5, dst='10.0.0.0/8')]

    def _to_b(self, footprint=('dead-ends',), edges=_EDGES):
        lib = _tracked_net(self.backend, footprint, edges, self.RULES)
        self.assertFalse(lib.is_reachable('src', '1', 'dB', '1', footprint_key='to-b'))
        return lib

    def test_a_change_into_the_drop_sink_is_not_reported(self):
        update = [_minus(self.RULES[0])]                       # 10/8: a -> drop
        default = self._to_b(())
        default.update(update)
        self.assertEqual(default.take_affected(), ['to-b'], "the default reports it")
        lib = self._to_b()
        lib.update(update)
        self.assertEqual(lib.take_affected(), [])

    def test_a_change_into_a_live_port_is_reported(self):
        lib = self._to_b()
        lib.update([_filter('b', 2, dst='192.168.0.0/16')])
        self.assertEqual(lib.take_affected(), ['to-b'])

    def test_an_unlinked_port_is_watched_for_a_link(self):
        lib = self._to_b()
        lib.update([_filter('c', 2, dst='192.168.0.0/16')])    # c has no link
        self.assertEqual(lib.take_affected(), [])
        lib.set_link('f', 'c', 'dB', '1', up=True)
        self.assertEqual(lib.take_affected(), ['to-b'])
        self.assertTrue(lib.is_reachable('src', '1', 'dB', '1'))

    def test_an_unlinked_port_that_is_the_target_is_no_dead_end(self):
        lib = _tracked_net(self.backend, ('dead-ends',), _EDGES, self.RULES)
        self.assertFalse(lib.is_reachable('src', '1', 'f', 'c', footprint_key='to-c'))
        lib.update([_filter('c', 2, dst='192.168.0.0/16')])
        self.assertEqual(lib.take_affected(), ['to-c'])
        self.assertTrue(lib.is_reachable('src', '1', 'f', 'c'))

    def test_a_reachable_query_still_sees_its_packets_dropped(self):
        lib = _tracked_net(self.backend, ('dead-ends',), _EDGES, self.RULES)
        self.assertTrue(lib.is_reachable('src', '1', 'dA', '1', footprint_key='to-a'))
        lib.update([_minus(self.RULES[0])])                    # 10/8: a -> drop
        self.assertEqual(lib.take_affected(), ['to-a'])


@require_or_skip(_ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestNddWitnessFootprints(TestWitnessFootprints):
    backend = 'ndd'


@require_or_skip(_ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestNddDeadEndFootprints(TestDeadEndFootprints):
    backend = 'ndd'


class TestFootprintModes(unittest.TestCase):

    def test_an_unknown_mode_is_refused(self):
        if not available():
            self.skipTest("JPype or the APKeep jar is unavailable")
        with self.assertRaises(ValueError):
            LibAPKeep(footprint=('witnesses',))

    def test_both_modes_by_default_coarse_on_request(self):
        if not available():
            self.skipTest("JPype or the APKeep jar is unavailable")
        self.assertEqual(LibAPKeep().footprint, ('witness', 'dead-ends'))
        self.assertEqual(LibAPKeep(footprint=()).footprint, ())

    def test_the_adapter_defaults_to_both_modes_on_apkeep_only(self):
        if not available():
            self.skipTest("JPype or the APKeep jar is unavailable")
        import logging
        from apkeep.adapter import APKeepAdapter
        log = logging.getLogger("test_apkeep_incremental_core")
        stamp = APKeepAdapter(log, engine='bdd').configuration_stamp()
        self.assertEqual(stamp['footprint'], ['witness', 'dead-ends'])
        stamp = APKeepAdapter(log, engine='bdd', footprint=()).configuration_stamp()
        self.assertEqual(stamp['footprint'], [])
        with self.assertRaises(ValueError):
            APKeepAdapter(log, engine='ndd', footprint=('witness',))


if __name__ == '__main__':
    unittest.main()
