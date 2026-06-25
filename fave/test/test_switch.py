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

""" Tests the switch CLI parsing helpers and the SwitchCommand wire model --
the pure string->model logic, exercised without the socket-driven main(). """

import unittest

from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from devices.switch import (
    fieldify, _fields_to_match, _commands_to_actions, SwitchCommand
)


class TestFieldify(unittest.TestCase):
    """ Tests OXM field-name mapping. """

    def test_maps_oxm_name_to_internal(self):
        field = fieldify(('tcp_dst', '80'))
        self.assertEqual(field.name, 'packet.upper.dport')
        self.assertEqual(field.value, '80')


class TestFieldsToMatch(unittest.TestCase):
    """ Tests parsing a ';'-separated field string into a Match. """

    def test_injects_ip_proto_for_transport_fields(self):
        """ A tcp_*/udp_* field also yields an ip_proto match. The protocol is
        canonicalized to its IANA number at RuleField construction (tcp -> 6). """
        match = _fields_to_match('tcp_dst=80')
        self.assertEqual(
            [(f.name, f.value) for f in match],
            [('packet.upper.dport', '80'), ('packet.ipv6.proto', '6')]
        )

    def test_plain_field_has_no_proto_injection(self):
        match = _fields_to_match('ipv6_src=2001:db8::1')
        self.assertEqual(
            [(f.name, f.value) for f in match],
            [('packet.ipv6.source', '2001:db8::1')]
        )

    def test_empty_field_string(self):
        self.assertEqual(_fields_to_match(''), [])


class TestCommandsToActions(unittest.TestCase):
    """ Tests parsing a ','-separated command string into rule actions. """

    def test_forward_action(self):
        actions = _commands_to_actions('fd=p1;p2')
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], Forward)
        self.assertEqual(actions[0].ports, ['p1', 'p2'])

    def test_rewrite_action(self):
        actions = _commands_to_actions('rw=tcp_dst:80')
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], Rewrite)
        self.assertEqual(
            [(f.name, f.value) for f in actions[0].rewrite],
            [('packet.upper.dport', '80')]
        )

    def test_empty_command_string(self):
        self.assertEqual(_commands_to_actions(''), [])


class TestSwitchCommand(unittest.TestCase):
    """ Tests the SwitchCommand wire object round-trip. """

    def test_to_from_json_roundtrip(self):
        rule = Rule(
            'sw', 'sw.1', 0,
            in_ports=['sw.1'],
            match=Match([RuleField('packet.upper.dport', '80')]),
            actions=[Forward(['sw.2'])],
        )
        command = SwitchCommand('sw', 'add_rule', [rule])
        self.assertEqual(
            SwitchCommand.from_json(command.to_json()).to_json(),
            command.to_json()
        )


if __name__ == '__main__':
    unittest.main()
