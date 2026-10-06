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

""" An `-o` match in a filter chain CONSTRAINS, and is modelled.

TODO.md item 13a is closed. `-o` used to be refused outright here, gated behind
`FAVE_ALLOW_OUT_IFACE`, on the reasoning that `devices/packet_filter.py` wires
`forward_filter -> routing -> post_routing`, so a filter chain runs BEFORE the
routing decision; the packet's `out_port` is wildcard at that point, `routing`
then WRITES it, and the narrowing is therefore overwritten -- "the match
constrains nothing".

**That reasoning was wrong, and the V5 campaign measured it wrong.** The
narrowing does its FILTERING before the rewrite happens, so the rule applies to
exactly the slice of the flow that will leave by that port, and the rewrite
afterwards is consistent with it. NetPlumber, ad6 and VeriFlow-FR all get both
polarities right on the suite's two `-o` workloads -- `wl_example`'s `-o`
ACCEPT, the only permit for `office -> internet`, and `wl_up`'s `-o` DROP pair,
anti-spoofing over its own entire /48, which must NOT apply to internal
traffic. APKeep was the sole exception, because its adapter dropped such rules;
it now resolves them against the FIB.

So these pin what holds now: `-o` generates, and it generates a constraint.
"""

import contextlib
import io
import os
import tempfile
import unittest

from iptables.generator import generate
from iptables.parser_singleton import PARSER


def _rules(*lines):
    """ PARSER.parse() takes a PATH, so the ruleset goes through a file. """
    handle, path = tempfile.mkstemp(suffix='-ruleset')
    try:
        with os.fdopen(handle, 'w') as out:
            out.write('\n'.join(lines) + '\n')
        return PARSER.parse(path)
    finally:
        os.unlink(path)


def _match_fields(model):
    return [field.name
            for rules in model.tables.values() for rule in rules
            for field in (rule.match or [])]


class TestOutInterfaceIsModelled(unittest.TestCase):
    """ It generates, and what it generates is a constraint. """

    def test_an_out_interface_in_a_forward_rule_generates(self):
        model = generate(_rules(
            'ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT'
        ), 'fw', None, ['1', '2', '3'])
        self.assertIn('out_port', _match_fields(model))

    def test_an_out_interface_in_an_output_rule_generates(self):
        # Needs an address and an INPUT policy: an OUTPUT-only ruleset raises
        # KeyError('input_filter') whether or not `-o` is present, which is a
        # separate pre-existing gap and not this test's subject.
        model = generate(_rules(
            'ip6tables -P INPUT DROP',
            'ip6tables -A OUTPUT -o 1 -d 2001:db8::1 -j DROP'
        ), 'fw', '2001:db8::ff', ['1', '2', '3'])
        self.assertIn('out_port', _match_fields(model))

    def test_the_port_is_the_devices_egress_port(self):
        """ Not a bare interface name: the value must name this device's port,
        or nothing downstream could resolve it against a FIB. """
        model = generate(_rules(
            'ip6tables -A FORWARD -o 2 -j ACCEPT'
        ), 'fw', None, ['1', '2', '3'])
        values = [str(field.value)
                  for rules in model.tables.values() for rule in rules
                  for field in (rule.match or []) if field.name == 'out_port']
        self.assertTrue(values)
        self.assertTrue(any('fw.2' in v for v in values), values)

    def test_a_vlan_qualified_out_interface_gives_both_halves(self):
        """ `-o eth1.110` is an egress port AND a dvlan match; both are real. """
        model = generate(_rules(
            'ip6tables -A FORWARD -o eth1.110 -i eth1.152 '
            '-s 2001:db8::1 -j ACCEPT'
        ), 'fw', None, ['eth1', '2', '3'])
        fields = _match_fields(model)
        self.assertIn('packet.ether.dvlan', fields)
        self.assertIn('out_port', fields)

    def test_no_opt_in_is_needed_and_none_is_consulted(self):
        """ The retired switch must neither be required for the new behaviour
        nor able to resurrect the old one. A vestigial flag that still does
        something is worse than one that does not exist. """
        for value in ('', '0', '1', 'false'):
            with self.subTest(value=value):
                os.environ['FAVE_ALLOW_OUT_IFACE'] = value
                try:
                    model = generate(_rules(
                        'ip6tables -A FORWARD -o 1 -j ACCEPT'
                    ), 'fw', None, ['1', '2', '3'])
                    self.assertIn('out_port', _match_fields(model))
                finally:
                    del os.environ['FAVE_ALLOW_OUT_IFACE']

    def test_nothing_is_announced_on_stderr(self):
        """ The per-device notice went with the refusal: there is no longer an
        infidelity for it to qualify. """
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            generate(_rules(
                'ip6tables -A FORWARD -o 1 -j ACCEPT'
            ), 'fw', None, ['1', '2', '3'])
        self.assertNotIn('NO CONSTRAINT', said.getvalue())
        self.assertNotIn('13a', said.getvalue())


class TestWhatStaysAllowed(unittest.TestCase):

    def test_an_in_interface_is_fine(self):
        """ The ingress port is known when the chain runs, so `-i` means what
        it says. """
        generate(_rules(
            'ip6tables -A FORWARD -i 1 -s 2001:db8::0/32 -j DROP'
        ), 'fw', None, ['1', '2', '3'])

    def test_a_rule_with_no_interface_match_is_fine(self):
        generate(_rules(
            'ip6tables -A FORWARD -d 2001:db8::101 -p tcp --dport 80 -j ACCEPT'
        ), 'fw', None, ['1', '2', '3'])

    def test_a_default_policy_is_fine(self):
        generate(_rules('ip6tables -P FORWARD DROP'), 'fw', None, ['1', '2', '3'])


if __name__ == '__main__':
    unittest.main()
