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

""" `protocol` names an IP protocol, and a service may omit the port
(TODO item 21).

Nothing checked the VALUE of `protocol`, and the three renderers then disagreed
about what to do with one they could not represent. Measured on
`examples/fml-paper-policy.txt`, which is the only file in the tree that writes
anything but `'tcp'` or `'udp'`:

    declared              roles_to_csv     to_iptables
    protocol = 'arp'      protocol:arp     KeyError('port')
    protocol = 1616       protocol:1616    TypeError (int + str)
    port = 22, no proto   port:22          NO RULE AT ALL

FaVe rejects the first two as well -- `normalize_ipv6_proto` knows six names --
so the matrix compiled into checks the verifier could not read. And an IP
protocol number is one byte, so 1616 is not one whatever the spelling.

THE THIRD ROW IS THE WORST and is not a crash. `serviceinfo` stayed empty and
the emission is guarded by `if serviceinfo`, so the rule vanished: under a
default-deny ruleset the generated firewall silently withheld traffic the policy
PERMITS. It no longer implements the specification it was derived from, which is
exactly what `bench/wl_generic_fw` exists to detect -- and cannot, because no
scenario there has a port-only service.

WHERE EACH IS REFUSED, and why the two differ. An unrepresentable protocol is
refused at the DECLARATION: no consumer can carry it, so there is nothing to
decide later. A port without a protocol is refused only when writing iptables:
FaVe matches `packet.upper.dport` regardless of the upper protocol, so it is
meaningful in the model and in the matrix, and only the firewall cannot express
it.

LAYER 2 IS OUT OF SCOPE, not forgotten: FPL says layer 2 with role attributes
(`vlan`), and a service-level `l2proto` would be the way to write ARP if a
policy ever needs it (owner, 2026-09-21).
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy, Service
from policy_builder import PolicyBuilder
from policy_exceptions import (
    PortWithoutProtocolException, UnknownProtocolException)


def _inventory(service_body, service_name='S', role_attr="ipv4 = '10.2.0.0/24'"):
    return """
def service %s
%send

def role A
    description = 'a'
    ipv4 = '10.1.0.0/24'
end

def role B
    description = 'b'
    %s
    offers %s
end

def policies (default: deny)
    A ---> B.%s
end
""" % (service_name, service_body, role_attr, service_name, service_name)


def _build(text):
    policy = Policy(strict=True)
    PolicyBuilder.build(text, policy)
    return policy


def _forward(policy):
    """ The access rules for the A -> B pair. Both endpoints are required:
    matching on the source alone also picks up the anti-spoofing DROP. """
    return [line for line in policy.to_iptables().splitlines()
            if '-A FORWARD' in line
            and '-s 10.1.0.0/24' in line and '-d 10.2.0.0/24' in line]


class TestOnlyAnIPProtocolIsAccepted(unittest.TestCase):

    def test_every_protocol_fave_knows_is_accepted(self):
        """ The permissive half first: refusing too much would be the same
        defect pointing the other way. """
        for protocol in Service.valid_protocols:
            policy = _build(_inventory("    protocol = '%s'\n" % protocol))
            self.assertEqual(
                policy.services['S'].attributes['protocol'], protocol)

    def test_a_layer_2_protocol_is_refused_and_says_why(self):
        """ `arp`, from `examples/fml-paper-policy.txt`. """
        with self.assertRaises(UnknownProtocolException) as caught:
            _build(_inventory("    protocol = 'arp'\n"))

        message = str(caught.exception)
        self.assertIn('arp', message)
        self.assertIn('tcp', message, "the message must name what IS allowed")

    def test_a_number_that_is_not_an_IP_PROTOCOL_is_refused(self):
        """ `protocol = 1616`, also from that file. An IP protocol number is
        one byte, so 1616 is not one under any reading -- and it crashed
        `to_iptables` with a TypeError rather than being rejected. """
        with self.assertRaises(UnknownProtocolException):
            _build(_inventory("    protocol = 1616\n"))

    def test_a_protocol_NUMBER_is_refused_even_when_it_is_valid(self):
        """ 6 is tcp, but both consumers map `protocol` to the same field
        through a NAME table, so a number would be dropped downstream rather
        than understood. Refusing is the honest answer until the vocabulary
        accepts numbers on both sides. """
        with self.assertRaises(UnknownProtocolException):
            _build(_inventory("    protocol = 6\n"))

    def test_the_refusal_names_the_service(self):
        """ An inventory can hold hundreds; "not an IP protocol" alone leaves
        the reader searching. """
        with self.assertRaises(UnknownProtocolException) as caught:
            _build(_inventory("    protocol = 'arp'\n", service_name='Weird'))

        self.assertIn('Weird', str(caught.exception))


class TestAProtocolWithoutAPort(unittest.TestCase):
    """ icmp and gre carry no port; the generator read `cond['port']` anyway. """

    def test_it_emits_the_protocol_alone(self):
        rules = _forward(_build(_inventory("    protocol = 'icmp'\n")))

        self.assertEqual(len(rules), 1, rules)
        self.assertIn('--protocol icmp', rules[0])
        self.assertNotIn('--dport', rules[0])
        self.assertNotIn('--sport', rules[0])

    def test_it_reaches_the_matrix_too(self):
        """ The CSV always rendered this shape; assert it still does, so the
        fix cannot be read as "protocol-only is now special". """
        csv = _build(_inventory("    protocol = 'gre'\n")).roles_to_csv()

        self.assertIn('(protocol:gre)', csv)

    def test_a_protocol_WITH_a_port_is_unchanged(self):
        rules = _forward(_build(
            _inventory("    protocol = 'tcp'\n    port = 80\n")))

        self.assertEqual(len(rules), 1, rules)
        self.assertIn('--protocol tcp --dport 80', rules[0])


class TestAPortWithoutAProtocol(unittest.TestCase):

    def test_the_firewall_refuses_it(self):
        """ THE SILENT ONE. It used to emit nothing and say nothing. """
        policy = _build(_inventory("    port = 22\n"))

        with self.assertRaises(PortWithoutProtocolException) as caught:
            policy.to_iptables()

        self.assertIn('22', str(caught.exception))
        self.assertIn('A', str(caught.exception))

    def test_but_the_matrix_still_carries_it(self):
        """ Deliberately NOT refused at the declaration: FaVe matches
        `packet.upper.dport` regardless of the upper protocol, so the shape is
        meaningful in the model. Only iptables cannot express it. """
        csv = _build(_inventory("    port = 22\n")).roles_to_csv()

        self.assertIn('(port:22)', csv)

    def test_the_rule_is_not_silently_dropped(self):
        """ Guards the specific regression: a refusal that were reverted to
        `serviceinfo = ""` would leave the firewall permitting LESS than the
        policy, with no error. """
        policy = _build(_inventory("    port = 22\n"))
        try:
            rules = _forward(policy)
        except PortWithoutProtocolException:
            return

        self.fail("no exception, and the rules generated were: %s" % rules)


if __name__ == '__main__':
    unittest.main()
