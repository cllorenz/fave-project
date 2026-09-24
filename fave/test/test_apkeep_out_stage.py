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

from apkeep.adapter import APKeepAdapter

_VLAN = 'packet.ether.vlan'
_PROTO = 'packet.ipv6.proto'
_SRC = 'packet.ipv4.source'
_FLAGS = 'packet.upper.tcp.flags'

# mid.a:110001 -> out.a:130001 -[perm]-> out.a:120001 -> in.b:100001
_EDGES = ["mid.a 110001 out.a 130001", "out.a 120001 in.b 100001"]


def _row(idx, match, ports, in_ports=('130001',)):
    return {'idx': idx, 'ports': list(ports), 'in_ports': list(in_ports),
            'match': dict(match), 'rw': {}}


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
    """ `tcp_flags` is the one field no APKeep element carries.

    Emitting the rule without it is an over-approximation, so it is RECORDED and
    logged rather than passed over -- OUT_STAGE_PLAN.md sec. 4.4 leaves
    implementing the field itself open. On wl_stanford every such rule is one of
    the 24 dead `established` permits on out.yoza/yozb.
    """

    def test_the_widening_is_recorded(self):
        adapter = _adapter([
            _row(1, {}, ['120001']),
            _row(2, {_VLAN: 78, _PROTO: 6, _FLAGS: '1xxxxxxx'}, ['120001']),
        ])
        adapter._build_stanford_faithful(list(_EDGES))
        self.assertEqual(len(adapter._out_stage_widened), 1)
        self.assertIn(_FLAGS, adapter._out_stage_widened[0])

    def test_the_rule_is_still_emitted_with_what_it_CAN_carry(self):
        """ Dropping the rule instead would understate the workload, which is
        the thing this whole step exists to stop doing. """
        adapter = _adapter([
            _row(1, {}, ['120001']),
            _row(2, {_VLAN: 78, _PROTO: 6, _FLAGS: '1xxxxxxx'}, ['120001']),
        ])
        adapter._build_stanford_faithful(list(_EDGES))
        self.assertEqual(len(adapter._out_stage_rules), 2)
        self.assertEqual(adapter._out_stage_rules[1].split()[17], '78')


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
