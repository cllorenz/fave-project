#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" Tests for the router config helpers (netmask -> CIDR and Cisco ACL parsing)
that determine the scope of generated ACL rules.
"""

import os
import tempfile
import unittest

from devices.router import _build_cidr, parse_cisco_acls, parse_cisco_interfaces


class TestBuildCidr(unittest.TestCase):
    """ Tests netmask/wildcard -> CIDR prefix derivation.

    For IPv4 the prefix is derived from the mask read as a number; a wildcard
    (inverse) mask is used directly, a standard netmask is flipped via
    inverse_netmask=True. This is exact for contiguous (valid CIDR) masks.
    """

    def test_ipv6_defaults_to_host_prefix(self):
        self.assertEqual(_build_cidr('2001:db8::1'), '2001:db8::1/128')

    def test_ipv6_keeps_explicit_prefix(self):
        self.assertEqual(_build_cidr('2001:db8::/32'), '2001:db8::/32')

    def test_ipv4_wildcard_mask(self):
        # 0.255.255.255 wildcard == /8.
        self.assertEqual(
            _build_cidr('10.0.0.0', '0.255.255.255', '4'), '10.0.0.0/8'
        )

    def test_ipv4_standard_mask_inverted(self):
        # A standard netmask must be inverted to be read as a wildcard.
        self.assertEqual(
            _build_cidr('10.0.0.0', '255.0.0.0', '4', inverse_netmask=True),
            '10.0.0.0/8'
        )
        self.assertEqual(
            _build_cidr('192.168.1.0', '255.255.255.0', '4', inverse_netmask=True),
            '192.168.1.0/24'
        )

    def test_ipv4_zero_mask_is_host(self):
        self.assertEqual(_build_cidr('1.2.3.4', '0.0.0.0', '4'), '1.2.3.4/0')

    def test_ipv4_any_address(self):
        self.assertEqual(
            _build_cidr('any', '0.255.255.255', '4'), '0.0.0.0/8'
        )

    def test_unknown_protocol_raises(self):
        with self.assertRaises(Exception):
            _build_cidr('1.2.3.4', proto='9')


class TestParseCiscoAcls(unittest.TestCase):
    """ Tests Cisco ACL parsing (token-count dispatch -> rule tuples). """

    def _parse(self, content):
        with tempfile.NamedTemporaryFile(
            'w', suffix='.acl', delete=False
        ) as aclf:
            aclf.write(content)
            path = aclf.name
        try:
            return parse_cisco_acls(path)
        finally:
            os.unlink(path)

    def test_none_file_returns_none(self):
        self.assertIsNone(parse_cisco_acls(None))

    def test_five_token_rule_source_only(self):
        acls = self._parse('access-list 101 permit 10.0.0.0 0.255.255.255\n')
        self.assertEqual(
            acls, {'101': [([('ipv4_src', '10.0.0.0/8')], 'permit')]}
        )

    def test_eight_token_rule_source_and_dest(self):
        acls = self._parse(
            'access-list 50 permit ip 10.1.0.0 0.0.255.255 10.2.0.0 0.0.0.255\n'
        )
        self.assertEqual(acls, {
            '50': [
                ([('ipv4_src', '10.1.0.0/16'), ('ipv4_dst', '10.2.0.0/24')],
                 'permit')
            ]
        })

    def test_non_acl_lines_ignored(self):
        acls = self._parse(
            '! a comment\n'
            'interface Eth0\n'
            'access-list 7 deny 192.168.0.0 0.0.255.255\n'
        )
        self.assertEqual(
            acls, {'7': [([('ipv4_src', '192.168.0.0/16')], 'deny')]}
        )

    def test_unknown_rule_format_raises(self):
        with self.assertRaises(Exception):
            self._parse('access-list 1 permit\n')  # too few tokens


class TestParseCiscoInterfaces(unittest.TestCase):
    """ Tests Cisco interface-config parsing into the five vlan/if maps. """

    def _parse(self, content):
        with tempfile.NamedTemporaryFile(
            'w', suffix='.cfg', delete=False
        ) as inf:
            inf.write(content)
            path = inf.name
        try:
            return parse_cisco_interfaces(path)
        finally:
            os.unlink(path)

    def test_full_config(self):
        # A vlan interface ('interface <label> <vlan>', 3 tokens) vs a physical
        # interface ('interface <name>', 2 tokens) with switchport membership.
        cfg = '\n'.join([
            'interface Vlan 10',
            '  description example.com',
            '  ip address 10.0.0.1 255.255.255.0',
            '  ip access-group 101 in',
            'interface Vlan 20',
            '  no ip address',
            'interface GigabitEthernet0/1',
            '  switchport access vlan 10',
            'interface GigabitEthernet0/2',
            '  switchport trunk allowed vlan 10,20',
            '',
        ])
        domain, ports, ips, acls, if_to_vlans = self._parse(cfg)

        self.assertEqual(domain, {'10': 'example.com'})
        self.assertEqual(ports, {'10': [], '20': []})
        # Standard netmask -> CIDR (via _build_cidr inverse); 'no ip address' -> None.
        self.assertEqual(ips, {'10': '10.0.0.1/24', '20': None})
        # access-group direction is prefixed to the acl id.
        self.assertEqual(acls, {'10': ['in_101'], '20': []})
        # access vlan -> single membership; trunk allowed vlan -> the list.
        self.assertEqual(if_to_vlans, {
            'GigabitEthernet0/1': [10],
            'GigabitEthernet0/2': [10, 20],
        })

    def test_description_before_interface_raises(self):
        """ A vlan-scoped line with no preceding 'interface <vlan>' asserts. """
        with self.assertRaises(AssertionError):
            self._parse('  description example.com\n')


if __name__ == '__main__':
    unittest.main()
