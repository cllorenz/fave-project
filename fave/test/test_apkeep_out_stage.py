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

""" The wl_stanford out stage is EMITTED, not collapsed (OUT_STAGE_PLAN.md
sec. 4.3).

Commit `2a36d4af` resolved the `mid.X -> out.X -> neighbour` chain statically and
threw the stage's match conditions away, because APKeep's only forwarding
primitive then was an in-port-blind destination trie. The stage is now one
FilterElement per ARRIVAL PORT, carrying that port's rules in index order.

**What this buys is COST, not correctness, and that is measured rather than
hoped.** wl_stanford's out-stage ACL is entirely dead -- a match-all sits first
on all 68 conditional arrival ports, hassel reads the tf files top-down with
first-match semantics (owner, 2026-09-24), and deleting the 2,002 rules behind
that match-all changes NetPlumber's own answer by nothing. So no verdict moves.
What changes is that APKeep is handed the workload NetPlumber is handed, instead
of one 2,683 rules smaller -- see `_cost_metrics`.

These are pure logic over a hand-built adapter state: no JVM, and no wl_stanford
generation. The end-to-end evidence (165/165 vs NetPlumber, unchanged) lives in
`bench/apkeep_out_stage_oracle.py` and the integration tier.
"""

import logging
import unittest

from apkeep.adapter import (APKeepAdapter, UntranslatedSemantics, _shadowed,
                           _filter_rule_string)
from apkeep.lib_ndd import LibNDD, available as ndd_available
from apkeep.lib_apkeep import LibAPKeep, available as bdd_available
from test.backend_gate import require_or_skip

_VLAN = 'packet.ether.vlan'
_PROTO = 'packet.ipv6.proto'
_SRC = 'packet.ipv4.source'
_FLAGS = 'packet.upper.tcp.flags'

# mid.a:110001 -> out.a:130001 -[perm]-> out.a:120001 -> in.b:100001
_EDGES = ["mid.a 110001 out.a 130001", "out.a 120001 in.b 100001"]


def _row(idx, match, ports, in_ports=('130001',), rw=None):
    return {'idx': idx, 'ports': list(ports), 'in_ports': list(in_ports),
            'match': dict(match), 'rw': dict(rw or {})}


def _adapter(rows):
    adapter = APKeepAdapter(logging.getLogger('test_apkeep_out_stage'),
                            faithful_vlan=True)
    adapter._out_perm = {'out.a': {'130001': {'120001'}}}
    adapter._fwd_table = {'out.a': list(rows)}
    return adapter


class TestTheOutStageBecomesElements(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # The wl_stanford shape in miniature: a match-all FIRST, then the ACL.
        adapter = _adapter([
            _row(1, {}, ['120001']),                                  # match-all
            _row(2, {_VLAN: 78, _PROTO: 6}, ['120001']),              # narrower permit
            _row(3, {_VLAN: 570, _SRC: '10.0.0.1/32'}, []),           # deny
        ])
        cls.edges, *_ = adapter._build_stanford_faithful(list(_EDGES))
        cls.adapter = adapter
        cls.rules = adapter._out_stage_rules

    def test_one_element_per_arrival_port(self):
        self.assertEqual(len(self.adapter._out_stage_elems), 1)

    def test_every_rule_is_emitted(self):
        """ The whole point of the change: the stage's rules reach the engine
        instead of being discarded with the collapse. """
        self.assertEqual(len(self.rules), 3)

    def test_the_mid_stage_now_feeds_the_ELEMENT_not_the_neighbour(self):
        elem = self.adapter._out_stage_elems[0]
        self.assertIn("mid.a 110001 %s in" % elem, self.edges)
        self.assertNotIn("mid.a 110001 in.b 100001", self.edges)

    def test_the_element_egresses_to_the_real_neighbour(self):
        elem = self.adapter._out_stage_elems[0]
        self.assertIn("%s 120001 in.b 100001" % elem, self.edges)

    def test_the_MATCH_ALL_outranks_the_rules_behind_it(self):
        """ hassel is top-down first-match and APKeep is higher-priority-wins,
        so rule 1 must carry the HIGHEST priority. This is what makes the
        emitted ACL correctly dead rather than newly active -- emitting it in
        the wrong order would change verdicts, which is the one way this change
        could do harm. """
        prios = [int(r.split()[16]) for r in self.rules]
        self.assertEqual(prios, sorted(prios, reverse=True))
        self.assertEqual(self.rules[0].split()[5], '120001')      # the match-all

    def test_the_narrower_permit_keeps_its_vlan_and_protocol(self):
        tokens = self.rules[1].split()
        self.assertEqual(tokens[17], '78')                        # vlan slot
        self.assertEqual((tokens[6], tokens[7]), ('6', '6'))      # proto

    def test_a_rule_with_no_forward_action_becomes_a_DROP(self):
        self.assertEqual(self.rules[2].split()[5], '__drop__')

    def test_nothing_was_widened_here(self):
        """ The control for the test below. """
        self.assertEqual(self.adapter._out_stage_widened, [])


class TestAnUnexpressibleMatchIsDECLARED(unittest.TestCase):
    """ A match no APKeep element carries is RECORDED and logged, never passed
    over in silence, and the rule is still emitted with what it CAN carry --
    dropping it would understate the workload, which is the thing this step
    exists to stop doing.

    **`tcp_flags` used to be the example here and no longer is**: step 4 gave
    both engines the field (`test_apkeep_tcp_flags.py`), so the widening it
    produced is gone and `_out_stage_widened` is empty on wl_stanford. The
    mechanism still matters for the next field the stage meets, so the case is
    kept with a field nothing carries.
    """

    _ETHER_SRC = 'packet.ether.source'

    def test_the_widening_is_recorded(self):
        adapter = _adapter([
            _row(1, {}, ['120001']),
            _row(2, {_VLAN: 78, self._ETHER_SRC: '00:11:22:33:44:55'},
                 ['120001']),
        ])
        adapter._build_stanford_faithful(list(_EDGES))
        self.assertEqual(len(adapter._out_stage_widened), 1)
        self.assertIn(self._ETHER_SRC, adapter._out_stage_widened[0])

    def test_the_rule_is_still_emitted_with_what_it_CAN_carry(self):
        adapter = _adapter([
            _row(1, {}, ['120001']),
            _row(2, {_VLAN: 78, self._ETHER_SRC: '00:11:22:33:44:55'},
                 ['120001']),
        ])
        adapter._build_stanford_faithful(list(_EDGES))
        self.assertEqual(len(adapter._out_stage_rules), 2)
        self.assertEqual(adapter._out_stage_rules[1].split()[17], '78')

    def test_tcp_flags_is_NO_LONGER_widened(self):
        """ The regression guard for step 4, from this side: the field that
        motivated this mechanism must not come back through it. """
        adapter = _adapter([
            _row(1, {}, ['120001']),
            _row(2, {_VLAN: 78, _PROTO: 6, _FLAGS: '1xxxxxxx'}, ['120001']),
        ])
        adapter._build_stanford_faithful(list(_EDGES))
        self.assertEqual(adapter._out_stage_widened, [])


class TestShadowing(unittest.TestCase):
    """ `_shadowed`: conservative, sound, and only valid for a FIRST-MATCH list. """

    def test_a_match_all_shadows_everything_after_it(self):
        rows = [_row(1, {}, ['120001']), _row(2, {_VLAN: 78}, ['120001'])]
        self.assertIsNone(_shadowed(rows, 0))
        self.assertIs(_shadowed(rows, 1), rows[0])

    def test_a_narrower_earlier_rule_shadows_nothing(self):
        """ The direction that matters: an earlier rule constraining MORE than a
        later one does not subsume it, and claiming otherwise would call a live
        rule dead. """
        rows = [_row(1, {_VLAN: 78, _PROTO: 6}, ['120001']),
                _row(2, {_VLAN: 78}, ['120001'])]
        self.assertIsNone(_shadowed(rows, 1))

    def test_a_different_value_shadows_nothing(self):
        rows = [_row(1, {_VLAN: 70}, ['120001']),
                _row(2, {_VLAN: 78}, ['120001'])]
        self.assertIsNone(_shadowed(rows, 1))

    def test_a_dropping_rule_shadows_too(self):
        """ Shadowing is about the MATCH race, not the action. """
        rows = [_row(1, {_VLAN: 78}, []), _row(2, {_VLAN: 78, _PROTO: 6}, ['1'])]
        self.assertIs(_shadowed(rows, 1), rows[0])


class TestARewriteGetsItsOwnEgressPort(unittest.TestCase):
    """ A NATElement is keyed on (device, port) and rewrites whatever leaves that
    port. It has no priority and no link to a rule, so it cannot ask whether the
    rule it came from won the first-match race -- hanging it on the rule's REAL
    egress rewrites traffic other rules forwarded. Measured on both engines, and
    live here, because all 45 out-stage resets share their port's single egress
    with the match-all that shadows them.

    A dedicated port fixes it by construction: the race is decided at the
    FilterElement, so only traffic that won via THIS rule leaves by this port.
    The port carries the match -- which is also why a dst-prefix `+ nat ... vlan`
    suffices, with no richer NAT grammar.
    """

    @classmethod
    def setUpClass(cls):
        adapter = _adapter([
            _row(1, {}, ['120001']),                               # match-all
            _row(2, {_VLAN: 864}, ['120001'], rw={_VLAN: 0}),      # shadowed reset
        ])
        (cls.edges, cls.nats, cls.nat_rules,
         _acls, _acl_rules) = adapter._build_stanford_faithful(list(_EDGES))
        cls.adapter = adapter
        cls.rules = adapter._out_stage_rules
        cls.elem = adapter._out_stage_elems[0]

    def test_the_plain_rule_keeps_the_real_egress(self):
        self.assertEqual(self.rules[0].split()[5], '120001')

    def test_the_rewriting_rule_forwards_to_a_DEDICATED_port(self):
        port = self.rules[1].split()[5]
        self.assertNotEqual(port, '120001')
        self.assertTrue(port.startswith('120001'))

    def test_a_nat_sits_on_that_port_and_carries_the_value(self):
        port = self.rules[1].split()[5]
        self.assertEqual(len(self.nat_rules), 1)
        tokens = self.nat_rules[0].split()
        self.assertEqual(tokens[:5], ['+', 'nat', self.elem, port, 'vlan'])
        self.assertEqual(tokens[7], '0')                     # the rewritten VLAN
        self.assertEqual(self.nats[self.elem], [port])

    def test_the_dedicated_port_reaches_the_SAME_neighbour(self):
        """ Otherwise the rewrite would be a black hole rather than a rewrite. """
        port = self.rules[1].split()[5]
        self.assertIn("%s %s in.b 100001" % (self.elem, port), self.edges)
        self.assertIn("%s 120001 in.b 100001" % self.elem, self.edges)

    def test_the_shadowed_rule_is_still_EMITTED(self):
        """ It is inert by construction -- nothing reaches its port -- and it is
        still charged, which is what sec. 7 asks for. Dropping it would
        understate the workload. """
        self.assertEqual(len(self.rules), 2)

    def test_it_is_reported_as_shadowed(self):
        """ Reported, not acted on: no part of the translation depends on it. """
        self.assertEqual(len(self.adapter._out_stage_shadowed), 1)


class TestAReachableRewriteIsCarriedToo(unittest.TestCase):
    """ The case the previous construction REFUSED. """

    def test_a_rule_that_can_fire_gets_its_port_and_nat(self):
        adapter = _adapter([
            _row(1, {_VLAN: 864}, ['120001'], rw={_VLAN: 0}),   # fires
            _row(2, {}, ['120001']),
        ])
        _e, nats, nat_rules, _a, _ar = adapter._build_stanford_faithful(
            list(_EDGES))
        self.assertEqual(len(nat_rules), 1)
        self.assertEqual(adapter._out_stage_shadowed, [])
        self.assertEqual(adapter._out_stage_rules[0].split()[5],
                         nat_rules[0].split()[3])

    def test_two_rules_writing_the_same_value_out_the_same_port_SHARE_one(self):
        """ Grouping by (egress, rewritten value). Sound because the NAT on a
        shared port applies to all of it, and every rule using the port writes
        the same value. Measured on wl_stanford it collapses nothing -- each of
        the 45 resets has its own egress -- so it is kept for the mechanism, not
        for a footprint win here. """
        adapter = _adapter([
            _row(1, {_VLAN: 864}, ['120001'], rw={_VLAN: 0}),
            _row(2, {_VLAN: 900}, ['120001'], rw={_VLAN: 0}),
            _row(3, {}, ['120001']),
        ])
        _e, nats, nat_rules, _a, _ar = adapter._build_stanford_faithful(
            list(_EDGES))
        self.assertEqual(len(nat_rules), 1)
        first, second = (r.split()[5] for r in adapter._out_stage_rules[:2])
        self.assertEqual(first, second)

    def test_a_rewrite_field_with_no_primitive_is_REFUSED(self):
        adapter = _adapter([
            _row(1, {}, ['120001']),
            _row(2, {_VLAN: 864}, ['120001'], rw={_PROTO: 17}),
        ])
        with self.assertRaises(UntranslatedSemantics) as caught:
            adapter._build_stanford_faithful(list(_EDGES))
        self.assertIn('no primitive', str(caught.exception))


class TestAnArrivalPortNoRuleNamesKeepsTheStaticResolution(unittest.TestCase):
    """ An element with no rules would default-drop, deleting a path the stage
    actually has. The permutation is kept for it instead. """

    def test_no_element_and_the_edge_goes_straight_through(self):
        adapter = _adapter([_row(1, {}, ['120001'], in_ports=['999999'])])
        edges, *_ = adapter._build_stanford_faithful(list(_EDGES))
        self.assertEqual(adapter._out_stage_elems, [])
        self.assertIn("mid.a 110001 in.b 100001", edges)


if __name__ == '__main__':
    unittest.main()


# --- and the same thing asked of the engines --------------------------------
#
# The classes above check rule STRINGS. These check that the construction means
# what it is supposed to mean, on both engines, using the real rule pair from
# `out.bbra_rtr.130013`:
#
#     idx=36  (match-all)   -> fd 120013
#     idx=49  vlan=864      -> rw vlan:0, fd 120013     <- SAME egress
#
# hassel is top-down first-match, so idx 36 always wins and the reset never
# happens. Hanging its NAT on 120013 would reset idx 36's traffic instead.
_E_SPLIT = ["mid p110013 oacl in", "oacl 120013 nbr p1", "oacl 120013r0 nbr p1"]


def _verdicts(rules, nats):
    """ (vlan 864 can arrive?, vlan 0 can arrive?) on (NDD, BDD). """
    ndd = LibNDD()
    ndd.build(rules, _E_SPLIT)
    bdd = LibAPKeep()
    bdd.init_in_memory("outsplit", _E_SPLIT, device_filters=["oacl"],
                       device_nats={"oacl": nats} if nats else None)
    bdd.run(rules)
    return tuple(
        (bool(ndd.is_reachable("mid", "p110013", "nbr", "p1", target_vlan=tv)),
         bool(bdd.is_reachable("mid", "p110013", "nbr", "p1", target_vlan=tv)))
        for tv in (864, 0))


@require_or_skip(ndd_available() and bdd_available(), "both engines are needed")
class TestTheSplitMeansWhatItShould(unittest.TestCase):

    def test_a_shadowed_rewrite_does_not_touch_the_winner(self):
        """ idx 36 forwards a vlan-864 packet untouched, so it must still arrive
        as 864. Put the NAT on the shared egress instead and both engines say
        False -- the reset was applied to traffic idx 36 forwarded. """
        rules = [
            _filter_rule_string('oacl', '120013', None, None, None, None, None,
                                None, 36),
            _filter_rule_string('oacl', '120013r0', None, None, None, None,
                                None, None, 49, vlan=864),
            "+ nat oacl 120013r0 vlan 0.0.0.0 0 0",
        ]
        vlan864, _vlan0 = _verdicts(rules, ["120013r0"])
        self.assertEqual(vlan864, (True, True))

    def test_the_MISPLACED_nat_is_what_breaks_it(self):
        """ The control that makes the test above mean something: the identical
        model with the NAT on the shared egress loses the vlan-864 packet. """
        rules = [
            _filter_rule_string('oacl', '120013', None, None, None, None, None,
                                None, 36),
            _filter_rule_string('oacl', '120013', None, None, None, None, None,
                                None, 49, vlan=864),
            "+ nat oacl 120013 vlan 0.0.0.0 0 0",
        ]
        vlan864, _vlan0 = _verdicts(rules, ["120013"])
        self.assertEqual(vlan864, (False, False))

    def test_a_reachable_rewrite_IS_applied(self):
        """ Swap the priorities so the vlan-864 rule wins: the reset must now
        happen -- 864 must not arrive, 0 must. This is the case the previous
        construction refused outright. """
        rules = [
            _filter_rule_string('oacl', '120013r0', None, None, None, None,
                                None, None, 36, vlan=864),
            _filter_rule_string('oacl', '120013', None, None, None, None, None,
                                None, 49),
            "+ nat oacl 120013r0 vlan 0.0.0.0 0 0",
        ]
        vlan864, vlan0 = _verdicts(rules, ["120013r0"])
        self.assertEqual(vlan864, (False, False))
        self.assertEqual(vlan0, (True, True))
