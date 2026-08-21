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

""" AD6_PLAN.md §5.4 Stage 0: Ad6Adapter's ACL/VLAN capture must not clobber
across devices.

wl_ifi has exactly one admission-checked router, so a flat vlan-keyed dict
(`_acl_in`/`_acl_out`: `{vlan: [...]}`, no device dimension at all) was never
wrong there. Stanford is 16 independent `in.X`/`out.X` devices that can reuse
the same VLAN number for unrelated admission groups -- a second device's
capture would silently clobber (or wrongly merge into) the first's under the
old flat scheme. This pins the fix (`_acl_devices`/`_acl_in`/`_acl_out`/
`_vlan_to_eport` keyed by device first, then VLAN) directly, at the
`Ad6Adapter` capture layer -- no ad6 binary/subprocess involved, no
benchmark inputs needed. """

import logging
import unittest

from ad6.adapter import Ad6Adapter
from rule.rule_model import Forward, Match, Rule, RuleField

_VLAN = 'packet.ether.vlan'
_SRC = 'packet.ipv4.source'
_DST = 'packet.ipv4.destination'


class _FakeModel:
    def __init__(self, node, tables):
        self.node = node
        self.tables = tables


def _acl_rule(idx, vlan, src, dst, permit=True):
    match = Match([
        RuleField(_VLAN, vlan),
        RuleField(_SRC, src),
        RuleField(_DST, dst),
    ])
    actions = [Forward(ports=['out.1'])] if permit else []
    return Rule('dev', 'acl_in', idx, match=match, actions=actions)


class TestAd6AdapterMultiDeviceAcl(unittest.TestCase):

    def setUp(self):
        self.engine = Ad6Adapter(logging.getLogger("test_multi_device_acl"))
        # Same VLAN number ("10") reused by two unrelated devices, with
        # DIFFERENT admission content -- the exact scenario a flat
        # {vlan: [...]} dict cannot represent without one clobbering the
        # other.
        dev_a = _FakeModel('devA', {
            'devA.acl_in': [_acl_rule(0, '10', '10.0.0.0/8', '10.0.0.0/8')],
        })
        dev_b = _FakeModel('devB', {
            'devB.acl_in': [_acl_rule(0, '10', '192.168.0.0/16', '192.168.0.0/16')],
        })
        for model in (dev_a, dev_b):
            self.engine.add_tables(model)
            self.engine.add_rules(model)
        self.ir = self.engine._build_ir()

    def test_both_devices_recorded(self):
        self.assertEqual(self.engine._acl_devices, {'devA', 'devB'})
        self.assertEqual(sorted(self.ir["acl_devices"]), ['devA', 'devB'])

    def test_acl_in_kept_separate_per_device(self):
        acl_in = self.ir["acl_in"]
        self.assertIn('devA', acl_in)
        self.assertIn('devB', acl_in)
        # Each device's own VLAN "10" group must hold only ITS OWN entry,
        # not both -- a flat {vlan: [...]} dict would append devB's entry
        # onto the SAME list as devA's (or a scalar _acl_device would have
        # silently forgotten devA entirely once devB was captured).
        self.assertEqual(len(acl_in['devA']['10']), 1)
        self.assertEqual(len(acl_in['devB']['10']), 1)
        self.assertNotEqual(acl_in['devA']['10'][0], acl_in['devB']['10'][0])


if __name__ == '__main__':
    unittest.main()
