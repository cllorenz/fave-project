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

""" `packet.upper.tcp.flags` as a real match field in BOTH engines
(OUT_STAGE_PLAN.md step 4).

It was the one field of wl_stanford's out stage no APKeep element could carry:
24 rules on `out.yoza_rtr`/`out.yozb_rtr`, every one of them Cisco's
`access-list 178 permit tcp any any established` compiled to
`tcp_flags=1xxxxxxx + ip_proto=6 + vlan=78`. Step 3 emitted those rules WITHOUT
the flags conjunct and declared the widening; this carries it.

**Ternary, not a value.** `established` fixes ONE bit and leaves seven free.
Encoding it as an exact value would match 1 of the 128 headers it should match --
a silent under-approximation, and the direction that loses traffic rather than
gaining it. Both engines take an MSB-first pattern where '1'/'0' fix a bit and
'x' leaves it free.

**Both engines together, or not at all.** The slot layout is the rule string's,
not an engine's, and item 23 step 0 plus OUT_STAGE_PLAN.md sec. 4.2 are two
recorded cases of one engine reading a slot the other dropped -- one rule string
meaning two different things.

**But here the DIFFERENTIAL is not what catches it, and that is worth knowing.**
Measured against deliberately rebuilt pre-step-4 jars: both per-engine classes
failed and `TestBothEnginesAgree` PASSED, because both engines ignored slot 19 in
exactly the same way. A differential only sees a defect the two engines disagree
about; a field neither carries is invisible to it. So the absolute verdicts below
are load-bearing here, and the differential guards the OTHER failure -- one
engine gaining the field while the other does not. Both kinds of assertion are
needed, for different defects.

Layout (slot 19, after `related` at 18):

    + filter <dev> filter 0 <out> <plo> <phi> <sip> <swild> <slo> <shi>
             <dip> <dwild> <dlo> <dhi> <prio> [vlan] [related] [tcp_flags]
"""

import logging
import unittest

from apkeep.adapter import APKeepAdapter, _filter_rule_string
from apkeep.lib_ndd import LibNDD, available as ndd_available
from apkeep.lib_apkeep import LibAPKeep, available as bdd_available
from test.backend_gate import require_or_skip

_FLAGS = 'packet.upper.tcp.flags'
_PROTO = 'packet.ipv6.proto'
_VLAN = 'packet.ether.vlan'

# src -> fw(p1), fw(p2) -> dst.
_EDGES = ["src p1 fw p1", "fw p2 dst p1"]


def _rule(out, prio, flags):
    return ("+ filter fw filter 0 %s 0 255 0.0.0.0 255.255.255.255 null null "
            "0.0.0.0 255.255.255.255 null null %d null null %s"
            % (out, prio, flags))


def _rules(flags):
    """ A flags-qualified DROP in front of an accept-all forward.

    Higher priority wins, so with the flags honoured only the matching half of
    the space is dropped and the rest still forwards; with the flags IGNORED the
    drop widens to the whole space and nothing gets through. That asymmetry is
    what makes reachability -- which is existential, and so normally blind to a
    match that only narrows a permit -- able to observe this field at all.
    """
    return [_rule("__drop__", 2000, flags), _rule("p2", 1000, "null")]


def _ndd(flags):
    engine = LibNDD()
    engine.build(_rules(flags), _EDGES)
    return bool(engine.is_reachable("src", "p1", "dst", "p1"))


def _bdd(flags):
    lib = LibAPKeep()
    lib.init_in_memory("tcpflags", _EDGES, device_filters=["fw"])
    lib.run(_rules(flags))
    return bool(lib.is_reachable("src", "p1", "dst", "p1"))


class TestTheRuleStringCarriesTheField(unittest.TestCase):
    """ Pure logic: the adapter emits slot 19, and an accept-all rule that names
    a flags pattern is not an identity. """

    def test_the_pattern_lands_in_slot_19(self):
        rule = _filter_rule_string('d', 'p2', None, None, None, None, None,
                                   None, 1, flags='1xxxxxxx')
        self.assertEqual(rule.split()[19], '1xxxxxxx')

    def test_absent_flags_leave_the_slot_null(self):
        rule = _filter_rule_string('d', 'p2', None, None, None, None, None,
                                   None, 1)
        self.assertEqual(rule.split()[19], 'null')

    def test_a_flags_qualified_pass_through_is_not_an_identity(self):
        """ `_elide_passthrough_filters` would otherwise contract it away and
        widen every path through it to every flag combination -- the same trap
        the VLAN slot has (sec. 4.2). """
        from apkeep.adapter import _is_acceptall_filter_rule
        rule = _filter_rule_string('d', 'p2', None, None, None, None, None,
                                   None, 1, flags='1xxxxxxx')
        self.assertFalse(_is_acceptall_filter_rule(rule.split()))

    def test_an_out_stage_rule_carrying_flags_is_no_longer_WIDENED(self):
        """ Step 3 emitted these rules without the conjunct and recorded the
        widening. Nothing should be recorded now. """
        adapter = APKeepAdapter(logging.getLogger('test_tcp_flags'),
                                faithful_vlan=True)
        adapter._out_perm = {'out.a': {'130001': {'120001'}}}
        adapter._fwd_table = {'out.a': [
            {'idx': 1, 'ports': ['120001'], 'in_ports': ['130001'],
             'match': {}, 'rw': {}},
            {'idx': 2, 'ports': ['120001'], 'in_ports': ['130001'],
             'match': {_VLAN: 78, _PROTO: 6, _FLAGS: '1xxxxxxx'}, 'rw': {}},
        ]}
        adapter._build_stanford_faithful(
            ["mid.a 110001 out.a 130001", "out.a 120001 in.b 100001"])
        self.assertEqual(adapter._out_stage_widened, [])
        self.assertEqual(adapter._out_stage_rules[1].split()[19], '1xxxxxxx')


@require_or_skip(ndd_available(), "the NDD jar is unavailable")
class TestNddTcpFlags(unittest.TestCase):

    def test_an_unqualified_drop_takes_everything(self):
        """ The control. Without it, an engine that forwarded nothing would look
        identical to one that honours the field. """
        self.assertFalse(_ndd("null"))

    def test_a_flags_qualified_drop_takes_only_its_half(self):
        self.assertTrue(_ndd("1xxxxxxx"))
        self.assertTrue(_ndd("0xxxxxxx"))


@require_or_skip(bdd_available(), "JPype or the APKeep jar is unavailable")
class TestBddTcpFlags(unittest.TestCase):

    def test_an_unqualified_drop_takes_everything(self):
        self.assertFalse(_bdd("null"))

    def test_a_flags_qualified_drop_takes_only_its_half(self):
        self.assertTrue(_bdd("1xxxxxxx"))
        self.assertTrue(_bdd("0xxxxxxx"))


@require_or_skip(ndd_available() and bdd_available(),
                 "both engines are needed for the differential")
class TestBothEnginesAgree(unittest.TestCase):
    """ Guards the defect class item 23 step 0 and sec. 4.2 both hit: one engine
    gaining a slot the other drops.

    Note what it does NOT guard, measured on pre-step-4 jars: with neither
    engine reading slot 19, this class passed while both per-engine classes
    failed. Agreement is not correctness when the agreement is on nothing.
    """

    def test_they_agree_on_every_pattern(self):
        for flags in ("null", "1xxxxxxx", "0xxxxxxx"):
            with self.subTest(flags=flags):
                self.assertEqual(_ndd(flags), _bdd(flags))


if __name__ == '__main__':
    unittest.main()
