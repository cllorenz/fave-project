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
(TABLE_SEMANTICS_PLAN.md §8, step 0; extended by OUT_STAGE_PLAN.md sec. 4.2).

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

**The `+ nat ... match` branch was a THIRD reader of the same slot and step 0
did not cover it** (OUT_STAGE_PLAN.md sec. 4.2). An address-rewrite NAT carries
the 5-tuple it is keyed on as a FilterElement body, and the NDD branch re-headed
that body and called bare `ruleToNDD` -- while the BDD side hands the same body
to `common.ACLRule`, whose `token[14]` IS the slot, and has therefore always
honoured it. So a NAT rewrote traffic on every VLAN under NDD and only the
matching one under BDD. Latent until `_filter_rule_string` gained a `vlan`
argument, because a first-match NAT reuses its own rule's body as the match --
which is exactly what sec. 4.2 turned on.

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


# --- the same slot, read through a NAT's match body -------------------------
#
# src -> nd(p1..p2) -> fw -> dst.  `nd` forwards only dst 10.0.0.0/8 and rewrites
# it onto 192.168.0.0/16; `fw` forwards only the REWRITTEN prefix. So the rewrite
# is what makes the destination reachable at all, and whether it applies under a
# given VLAN is directly observable.
_NAT_EDGES = ["src p1 nd p1", "nd p2 fw p1", "fw p2 dst p1"]


def _body(vlan_token):
    """ A FilterElement body matching dst 10.0.0.0/8, with slot 17 set. """
    return ("filter 0 p2 0 255 0.0.0.0 255.255.255.255 null null "
            "10.0.0.0 0.255.255.255 null null 1000 %s null" % vlan_token)


def _nat_rules(vlan_token):
    return [
        "+ filter nd " + _body("null"),
        "+ nat nd p2 match dst 192.168.0.0 16 " + _body(vlan_token),
        ("+ filter fw filter 0 p2 0 255 0.0.0.0 255.255.255.255 null null "
         "192.168.0.0 0.0.255.255 null null 1000 null null"),
    ]


def _ndd_nat_verdicts(vlan_token):
    eng = LibNDD()
    eng.build(_nat_rules(vlan_token), _NAT_EDGES)
    return tuple(
        bool(eng.is_reachable("src", "p1", "dst", "p1", target_vlan=tv))
        for tv in (None, 78, 20)
    )


def _bdd_nat_verdicts(vlan_token):
    lib = LibAPKeep()
    lib.init_in_memory("natvlanslot", _NAT_EDGES,
                       device_filters=["nd", "fw"], device_nats={"nd": ["p2"]})
    lib.run(_nat_rules(vlan_token))
    return tuple(
        bool(lib.is_reachable("src", "p1", "dst", "p1", target_vlan=tv))
        for tv in (None, 78, 20)
    )


@require_or_skip(ndd_available() and bdd_available(),
                 "both engines are needed for the differential")
class TestVlanSlotInANatMatchBody(unittest.TestCase):
    """ The third reader of slot 17: a NAT keyed on a FilterElement body. """

    def test_an_unqualified_nat_rewrites_on_every_vlan(self):
        """ The control. Without it, an engine that rewrote nothing would pass
        the test below. """
        self.assertEqual(_ndd_nat_verdicts("null"), (True, True, True))
        self.assertEqual(_bdd_nat_verdicts("null"), (True, True, True))

    def test_a_vlan_qualified_nat_rewrites_only_that_vlan(self):
        """ Measured on a pre-fix jar: NDD (True, True, True), BDD
        (True, True, False) -- the NAT applied on every VLAN under one engine
        and only vlan 78 under the other. """
        self.assertEqual(_ndd_nat_verdicts("78"), (True, True, False))

    def test_both_engines_agree(self):
        """ As above, the differential is what makes it a defect rather than a
        design choice. """
        self.assertEqual(_ndd_nat_verdicts("78"), _bdd_nat_verdicts("78"))


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


# --- the probe-untag asymmetry (TODO item 27) -------------------------------
#
# The two engines disagree about what arriving at a PROBE means for VLAN, and
# three findings used to rest on that being unmeasured. It is measured here, on
# a toy model, in milliseconds -- the earlier attempts tried to observe it
# through faithful wl_stanford, which does not finish on BDD.
#
#   NDD existentially quantifies VLAN out of any `probe.*` device before the
#   arrival constraint applies (a host on an access port receives the frame
#   untagged). BDD takes the constraint literally.
#
# Neither is "the bug": what was wrong was the ADAPTER forcing `target_vlan=0`
# at a faithful wl_stanford probe, because the reference model does not enforce
# that either -- clearing `vlan=0` on all 16 of wl_stanford's probes leaves
# NetPlumber at 165 pairs. The adapter no longer forces it, so this asymmetry
# is now inert for FaVe. Pinned so it cannot change unnoticed.
_PROBE_EDGES = ["src p1 fw p1", "fw p2 %s p1"]


def _probe_verdicts(dest):
    """ (target_vlan=5, target_vlan=0) on (NDD, BDD), with traffic that leaves
    carrying vlan 5. """
    edges = ["src p1 fw p1", "fw p2 %s p1" % dest]
    rules = [("+ filter fw filter 0 p2 0 255 0.0.0.0 255.255.255.255 null null "
              "0.0.0.0 255.255.255.255 null null 1000 null null null"),
             "+ nat fw p2 vlan 0.0.0.0 0 5"]
    ndd = LibNDD()
    ndd.build(rules, edges)
    bdd = LibAPKeep()
    bdd.init_in_memory("probevlan", edges, device_filters=["fw"],
                       device_nats={"fw": ["p2"]})
    bdd.run(rules)
    return tuple(
        (bool(ndd.is_reachable("src", "p1", dest, "p1", target_vlan=tv)),
         bool(bdd.is_reachable("src", "p1", dest, "p1", target_vlan=tv)))
        for tv in (5, 0)
    )


@require_or_skip(ndd_available() and bdd_available(), "both engines are needed")
class TestProbeUntagAsymmetry(unittest.TestCase):

    def test_at_an_ORDINARY_device_the_engines_agree(self):
        """ The control. Traffic leaves carrying vlan 5, so requiring vlan 0 at
        arrival is unsatisfiable -- on both engines. """
        vlan5, vlan0 = _probe_verdicts("dst")
        self.assertEqual(vlan5, (True, True))
        self.assertEqual(vlan0, (False, False))

    def test_at_a_PROBE_they_do_not(self):
        """ NDD untags and answers True; BDD is literal and answers False. """
        vlan5, vlan0 = _probe_verdicts("probe.x")
        self.assertEqual(vlan5, (True, True))
        self.assertEqual(vlan0, (True, False))
