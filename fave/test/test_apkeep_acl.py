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

""" Validates the APKeep ACL mechanic the wl_ifi ACL translation rests on
(APKEEP_BACKEND.md, P4): an ACLElement spliced into the forwarding path via the
L1-link naming convention, plus source-IP-seeded reachability.

A single router r forwards 10.0.0.0/8 to port 1 (where probe B sits); source A
enters via an ingress ACL on port 2 that denies src 192.168.0.0/16 and permits
the rest. The links splice the ACL node between A and r (A -> r_inACL_*_in's
inport; the ACL's "permit" port -> r port 2; denied traffic dies at the unwired
"deny" port). Reachability must be seeded with the injected source's src-IP, or
the ACL packet space is the full space and the deny never bites.

Checks: deny-class source is unreachable, permit-class source is reachable, and
priority is higher-wins (the specific deny outranks the catch-all permit, i.e.
cisco first-match maps to descending priority). """

import logging
import unittest

from apkeep.lib_apkeep import LibAPKeep, available
from test.backend_gate import require_or_skip


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestAPKeepACL(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        logging.getLogger("test_apkeep_acl").setLevel(logging.WARNING)
        cls.lib = LibAPKeep()
        edges = [
            "A 1 r_inACL_p2_in inport",   # source A -> ACL node input
            "r_inACL_p2_in permit r 2",   # ACL "permit" port -> router ingress 2
            "r 1 B 1",                    # router egress 1 -> probe B
        ]
        cls.lib.init_in_memory(
            "acltest", edges, fwd_devices=["r"], device_acls={"r": ["inACL"]}
        )
        # "+ acl <element> <list> <num> <permit|deny> <protoLo> <protoHi>
        #  <src> <srcWild> <sPortLo> <sPortHi> <dst> <dstWild> <dPortLo> <dPortHi> <prio>"
        # cisco wildcard 0.0.255.255 == /16; deny outranks permit (higher prio).
        cls.lib.run([
            "+ fwd r 167772160 8 1 8",    # 10.0.0.0/8 -> port 1
            "+ acl r_inACL acl 0 deny 0 255 192.168.0.0 0.0.255.255 "
            "null null 0.0.0.0 255.255.255.255 null null 200",
            "+ acl r_inACL acl 0 permit 0 255 0.0.0.0 255.255.255.255 "
            "null null 0.0.0.0 255.255.255.255 null null 100",
        ])

    def test_denied_source_unreachable(self):
        # 192.168.1.0/24 is inside the denied 192.168.0.0/16.
        self.assertFalse(self.lib.is_reachable(
            "A", "1", "B", "1", src_prefix=0xC0A80100, src_len=24))

    def test_permitted_source_reachable(self):
        # 1.2.3.0/24 is permitted and 10/8-routable to B.
        self.assertTrue(self.lib.is_reachable(
            "A", "1", "B", "1", src_prefix=0x01020300, src_len=24))

    def test_unseeded_overapproximates(self):
        # Without a src seed the ACL space is full, so the permit always exists:
        # reachability over-approximates (why source-IP seeding is required).
        self.assertTrue(self.lib.is_reachable("A", "1", "B", "1"))


if __name__ == '__main__':
    unittest.main()
