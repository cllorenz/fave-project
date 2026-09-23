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

""" The VLAN slot of a `+ filter` rule means the same thing to both engines
(TABLE_SEMANTICS_PLAN.md §8, step 0).

A FilterElement rule string carries an optional VLAN token in slot 17:

    + filter <dev> filter 0 <out> <plo> <phi> <sip> <swild> <slo> <shi>
             <dip> <dwild> <dlo> <dhi> <prio> [vlan] [related]

The BDD engine has always honoured it -- `FilterElement.encodeOneRule` encodes
through `ACLRule`, whose `token[14]` IS this slot (the P9a VLAN match) -- while
the NDD engine ignored it: `ruleToNDD` reads tokens 6..15 and `related` at 18
and never touched 17, and only the `+ acl` branch conjoined `vlanPred(t[17])`.
So the same rule string meant two different things depending on the engine.

It cost nothing while `_filter_rule_string` always wrote `null` there, which is
why it went unnoticed; it would have cost a silently over-permissive NDD model
the moment anyone emitted a real tag. Both branches now share `withVlanSlot`.

THE TRAP THAT MADE THE FIRST MEASUREMENT OF THIS WRONG, recorded because it will
catch the next person too: the NDD engine existentially quantifies VLAN out of
any device whose name starts with `probe.` (a host on an access port receives
the frame untagged), and it does so BEFORE the `target_vlan` arrival constraint
is applied. A test that pins the arrival VLAN *at a probe* therefore cannot
observe a VLAN constraint on NDD at all, and reports "ignored" whatever the
filter rule says. The destination here is deliberately named `dst`, not
`probe.dst`.
"""

import logging
import unittest

from apkeep.lib_ndd import LibNDD, available as ndd_available
from apkeep.lib_apkeep import LibAPKeep, available as bdd_available
from test.backend_gate import require_or_skip

# src -> fw(p1), fw(p2) -> dst. One FilterElement, one accept-all rule out p2.
_EDGES = ["src p1 fw p1", "fw p2 dst p1"]


def _rule(vlan_token):
    """ One accept-all FilterElement rule out of `p2`, with slot 17 set. """
    return ("+ filter fw filter 0 p2 0 255 0.0.0.0 255.255.255.255 null null "
            "0.0.0.0 255.255.255.255 null null 1000 %s null" % vlan_token)


def _ndd_verdicts(vlan_token):
    """ (unconstrained, arrival vlan=10, arrival vlan=20) on the NDD engine. """
    eng = LibNDD()
    eng.build([_rule(vlan_token)], _EDGES)
    return tuple(
        bool(eng.is_reachable("src", "p1", "dst", "p1", target_vlan=tv))
        for tv in (None, 10, 20)
    )


def _bdd_verdicts(vlan_token):
    """ The same three questions on the BDD engine. """
    lib = LibAPKeep()
    lib.init_in_memory("vlanslot", _EDGES, device_filters=["fw"])
    lib.run([_rule(vlan_token)])
    return tuple(
        bool(lib.is_reachable("src", "p1", "dst", "p1", target_vlan=tv))
        for tv in (None, 10, 20)
    )


@require_or_skip(ndd_available(), "the NDD jar is unavailable")
class TestNddVlanSlot(unittest.TestCase):
    """ NDD: slot 17 constrains the traffic a filter rule forwards. """

    def test_an_unqualified_rule_leaves_vlan_free(self):
        """ `null` in slot 17 constrains nothing -- the control, without which
        the test below could pass on an engine that dropped everything. """
        self.assertEqual(_ndd_verdicts("null"), (True, True, True))

    def test_a_vlan_qualified_rule_constrains_what_it_forwards(self):
        """ A rule matching vlan 10 forwards only vlan-10 traffic, so arrival
        under vlan 20 is unreachable while vlan 10 still is. Before the fix the
        third verdict was True. """
        self.assertEqual(_ndd_verdicts("10"), (True, True, False))


@require_or_skip(bdd_available(), "JPype or the APKeep jar is unavailable")
class TestBddVlanSlot(unittest.TestCase):
    """ BDD: the same, which it already did -- pinned so it stays the baseline. """

    def test_an_unqualified_rule_leaves_vlan_free(self):
        self.assertEqual(_bdd_verdicts("null"), (True, True, True))

    def test_a_vlan_qualified_rule_constrains_what_it_forwards(self):
        self.assertEqual(_bdd_verdicts("10"), (True, True, False))


@require_or_skip(ndd_available() and bdd_available(),
                 "both engines are needed for the differential")
class TestVlanSlotDifferential(unittest.TestCase):
    """ The assertion that actually guards the defect: the two engines must
    answer the SAME question of the same rule string.

    Either engine alone can be self-consistently wrong. The divergence is what
    made this a defect rather than a design choice, so the differential -- not
    the absolute verdicts above -- is what must not regress.
    """

    def test_both_engines_agree_on_an_unqualified_rule(self):
        self.assertEqual(_ndd_verdicts("null"), _bdd_verdicts("null"))

    def test_both_engines_agree_on_a_vlan_qualified_rule(self):
        """ This is the one that failed: NDD said (True, True, True) where BDD
        said (True, True, False). """
        self.assertEqual(_ndd_verdicts("10"), _bdd_verdicts("10"))


if __name__ == '__main__':
    unittest.main()
