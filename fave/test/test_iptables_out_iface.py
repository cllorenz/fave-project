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

""" An `-o` match in a FORWARD or OUTPUT rule is refused, loudly.

`devices/packet_filter.py` wires the pipeline `forward_filter -> routing ->
post_routing`, so a filter chain runs BEFORE the routing decision. At that point
the packet's `out_port` field is still wildcard: matching `-o <iface>` does not
fail, it NARROWS the header space, and the routing table then WRITES `out_port`
and overwrites the narrowing. The match therefore constrains nothing.

Linux is the other way round -- netfilter routes before FORWARD and before
OUTPUT -- so a ruleset written for Linux means something FaVe silently does not
model. Found on wl_example, where

    ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT

is how `Office <->> Internet` is written: permit the office subnet out port 1,
the INTERNET port. Modelled as no constraint it reduces to "accept anything from
the office subnet", and the DMZ became reachable on every port and protocol --
261 complement violations, which dropped to 0 when the rule was removed
(TODO.md item 13).

REFUSING IS NOT THE FIX, it is the honest interim. Reordering the pipeline so
routing precedes the filters is the faithful answer and is not trivial; see item
13a. Until then a ruleset whose meaning FaVe cannot represent must say so rather
than be quietly modelled as something weaker or stronger than it is -- the
direction of the error follows the target, `ACCEPT` over-permitting and `DROP`
over-restricting.

`FAVE_ALLOW_OUT_IFACE=1` overrides the refusal so the three affected workloads
(wl_example, wl_up, wl_tum) stay runnable while item 13a is decided. It restores
the OLD behaviour exactly -- the match is modelled as no constraint -- and says
so once per device, with a count. The difference from before is only that it can
no longer happen by accident. **It exists to be deleted**: once routing precedes
the filter chains, `-o` becomes expressible and both the refusal and the
override should go.

`-i` is unaffected: the ingress port IS known when the chain runs.
"""

import contextlib
import io
import os
import tempfile
import unittest

from iptables.generator import OutInterfaceUnsupported, generate
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


class TestRefusal(unittest.TestCase):

    def test_an_out_interface_in_a_forward_rule_is_refused(self):
        with self.assertRaises(OutInterfaceUnsupported):
            generate(_rules(
                'ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT'
            ), 'fw', None, ['1', '2', '3'])

    def test_an_out_interface_in_an_output_rule_is_refused(self):
        """ OUTPUT routes first in Linux too, and FaVe wires
        `output_filter_accept -> routing_in` exactly like the forward path. """
        with self.assertRaises(OutInterfaceUnsupported):
            generate(_rules(
                'ip6tables -A OUTPUT -o 1 -d 2001:db8::1 -j ACCEPT'
            ), 'fw', None, ['1', '2', '3'])

    def test_the_message_names_the_rule_and_says_why(self):
        try:
            generate(_rules(
                'ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT'
            ), 'fw', None, ['1', '2', '3'])
        except OutInterfaceUnsupported as error:
            message = str(error)
        else:
            self.fail('expected OutInterfaceUnsupported')

        self.assertIn('-o', message)
        self.assertIn('routing', message)
        self.assertIn('item 13', message)

    def test_a_vlan_qualified_out_interface_is_refused_too(self):
        """ `-o eth1.110` also yields a `dvlan` match, which routing does NOT
        overwrite -- so such a rule is PARTIALLY modelled, which is a worse
        thing to be quiet about than a wholly ignored one. """
        with self.assertRaises(OutInterfaceUnsupported):
            generate(_rules(
                'ip6tables -A FORWARD -o eth1.110 -i eth1.152 '
                '-s 2001:db8::1 -j ACCEPT'
            ), 'fw', None, ['1', '2', '3'])


class TestTheOptOut(unittest.TestCase):
    """ `FAVE_ALLOW_OUT_IFACE=1`: run anyway, with the infidelity stated. """

    def setUp(self):
        self._saved = os.environ.get('FAVE_ALLOW_OUT_IFACE')
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop('FAVE_ALLOW_OUT_IFACE', None)
        else:
            os.environ['FAVE_ALLOW_OUT_IFACE'] = self._saved

    def _generate(self):
        return generate(_rules(
            'ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT'
        ), 'fw', None, ['1', '2', '3'])

    def test_set_to_one_it_generates_instead_of_raising(self):
        os.environ['FAVE_ALLOW_OUT_IFACE'] = '1'
        self.assertIsNotNone(self._generate())

    def test_unset_it_still_refuses(self):
        os.environ.pop('FAVE_ALLOW_OUT_IFACE', None)
        with self.assertRaises(OutInterfaceUnsupported):
            self._generate()

    def test_an_empty_value_is_not_an_opt_in(self):
        """ An exported-but-empty variable is a common accident and must not
        silently re-enable a known infidelity. """
        os.environ['FAVE_ALLOW_OUT_IFACE'] = ''
        with self.assertRaises(OutInterfaceUnsupported):
            self._generate()

    def test_zero_and_false_are_not_opt_ins(self):
        for value in ('0', 'false', 'False', 'no'):
            os.environ['FAVE_ALLOW_OUT_IFACE'] = value
            with self.assertRaises(OutInterfaceUnsupported):
                self._generate()

    def test_it_says_so_on_stderr_with_a_count(self):
        os.environ['FAVE_ALLOW_OUT_IFACE'] = '1'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self._generate()
        said = stderr.getvalue()

        self.assertIn('FAVE_ALLOW_OUT_IFACE', said)
        self.assertIn('1', said)
        self.assertIn('fw', said)

    def test_the_vlan_half_still_survives_under_the_opt_out(self):
        """ `-o eth1.110` also yields a dvlan match, and THAT is a real header
        field routing does not overwrite. Only the port half is lost. """
        os.environ['FAVE_ALLOW_OUT_IFACE'] = '1'
        model = generate(_rules(
            'ip6tables -A FORWARD -o eth1.110 -i eth1.152 '
            '-s 2001:db8::1 -j ACCEPT'
        ), 'fw', None, ['eth1', '2', '3'])

        fields = [
            field.name
            for rules in model.tables.values() for rule in rules
            for field in (rule.match or [])
        ]
        self.assertIn('packet.ether.dvlan', fields)


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
