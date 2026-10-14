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

""" SwitchModel and RouterModel built by hand, and the switch CLI's `main()`
with the aggregator connection mocked (the message it would send is pinned).

Covers the switch's JSON/buffer/diff contract, the router's pipeline built
from ACLs, VLAN bindings, NAT pools and routes, its routing-table updates, and
the Cisco ACL parser's six-token form. test_switch.py and test_router.py cover
the CLI string helpers, `_build_cidr` and the interface parser.
"""

import json
import os
import tempfile
import unittest

from unittest import mock

import devices.switch as switch_mod

from devices.abstract_device import LPM
from devices.router import (
    RouterModel, _build_cidr, parse_cisco_acls, parse_cisco_interfaces,
)
from devices.switch import SwitchModel
from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX


def _fields(rule):
    return [(f.name, f.value) for f in rule.match]


class TestSwitchModel(unittest.TestCase):
    """ One table per switch; rules are re-homed into it. """

    def _rule(self, idx, port='sw.2'):
        return Rule('sw', 7, idx, match=Match([RuleField('packet.upper.dport', '80')]),
                    actions=[Forward([port])])

    def test_json_round_trip_with_table_ids(self):
        switch = SwitchModel('sw', ports=['1', '2'], rules=[self._rule(0)],
                             table_ids={'sw.1': 3})
        j = switch.to_json()
        self.assertEqual(j['table_ids'], {'sw.1': 3})
        back = SwitchModel.from_json(json.dumps(j))
        self.assertEqual(back.table_ids, {'sw.1': 3})
        self.assertEqual(back.to_json(), j)
        self.assertNotIn('table_ids', SwitchModel('sw').to_json())

    def test_add_rules_rehome_the_rule_into_the_single_table(self):
        switch = SwitchModel('sw', ports=['1', '2'])
        rule = self._rule(0)
        switch.add_rules([rule])
        self.assertEqual(rule.tid, 'sw.1')
        self.assertEqual(switch._adds['sw.1'], [rule])

    def test_remove_and_update(self):
        switch = SwitchModel('sw', ports=['1'], rules=[self._rule(0), self._rule(1, 'sw.3')])
        switch.remove_rule(0)
        self.assertEqual(switch._deletes, [0])
        self.assertEqual([r.idx for r in switch.tables['sw.1']], [1])
        new = self._rule(5)
        switch.update_rule(0, new)
        self.assertEqual(switch._deletes, [0, 0])
        self.assertEqual(switch.tables['sw.1'], [])
        self.assertEqual(switch._adds['sw.1'], [new])

    def test_diff_is_the_add_buffer(self):
        switch = SwitchModel('sw', ports=['1'])
        rule = self._rule(0)
        switch.add_rules([rule])
        diff = switch - SwitchModel('sw', ports=['1'])
        self.assertIsInstance(diff, SwitchModel)
        self.assertEqual(diff.tables, {'sw.1': [rule]})


class TestSwitchMain(unittest.TestCase):
    """ `devices.switch.main` sends one SwitchCommand per call. """

    def setUp(self):
        self.sent = []
        self.conn = mock.MagicMock(name='conn')
        connect = mock.patch.object(switch_mod, 'connect_to_fave', return_value=self.conn)
        send = mock.patch.object(
            switch_mod, 'fave_sendmsg',
            side_effect=lambda _c, data: self.sent.append(json.loads(data)))
        self.connect = connect.start()
        send.start()
        self.addCleanup(connect.stop)
        self.addCleanup(send.stop)

    def _main(self, argv):
        switch_mod.main(argv)
        self.assertEqual(len(self.sent), 1)
        self.conn.close.assert_called_once_with()
        return self.sent[0]

    def test_add_one_rule(self):
        msg = self._main(['-a', '-n', 'sw', '-t', '1', '-i', '3', '-p', 'sw.1,sw.2',
                          '-f', 'ipv6_dst=2001:db8::1;tcp_dst=22', '-c', 'fd=sw.2'])
        self.connect.assert_called_once_with(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
        self.assertEqual((msg['type'], msg['node'], msg['command']),
                         ('switch_command', 'sw', 'add_rules'))
        [rule] = msg['rules']
        self.assertEqual((rule['tid'], rule['idx'], rule['in_ports']),
                         ('sw.1', 3, ['sw.1', 'sw.2']))
        self.assertEqual([(f['name'], f['value']) for f in rule['match']['fields']],
                         [('packet.ipv6.destination', '2001:db8::1'),
                          ('packet.upper.dport', '22'), ('packet.ipv6.proto', '6')])
        self.assertEqual(rule['actions'], [{'name': 'forward', 'ports': ['sw.2']}])

    def test_add_a_batch_of_rules(self):
        msg = self._main(['-U', '-r',
                          'sw$1$1$sw.1$ipv6_dst=2001:db8::1$fd=sw.2#'
                          'sw$1$2$$$rw=vlan:5,fd=sw.3'])
        self.connect.assert_called_once_with(FAVE_DEFAULT_UNIX)
        self.assertEqual(msg['command'], 'add_rules')
        first, second = msg['rules']
        self.assertEqual((first['tid'], first['idx'], first['in_ports']), (1, 1, ['sw.1']))
        self.assertEqual((second['idx'], second['in_ports']), (2, []))
        self.assertEqual([a['name'] for a in second['actions']], ['rewrite', 'forward'])

    def test_delete(self):
        msg = self._main(['-d', '-n', 'sw', '-i', '4'])
        self.assertEqual(msg['command'], 'remove_rule')
        [rule] = msg['rules']
        self.assertEqual((rule['tid'], rule['idx'], rule['actions']), ('sw.1', 4, []))

    def test_update(self):
        msg = self._main(['-u', '-n', 'sw', '-t', '2', '-i', '1', '-c', 'fd=sw.9'])
        self.assertEqual(msg['command'], 'update_rule')
        [rule] = msg['rules']
        self.assertEqual((rule['tid'], rule['idx']), ('sw.2', 1))
        self.assertEqual(rule['actions'], [{'name': 'forward', 'ports': ['sw.9']}])


class TestRouterModel(unittest.TestCase):
    """ The router pipeline: pre_routing binds VLANs, acl_in/acl_out hold the
    ACLs per VLAN (and NAT rewrites), routing tags the egress. """

    def setUp(self):
        self.acls = {
            '10': [([('ipv4_src', '10.0.1.0/24')], 'permit'),
                   ([('ipv4_src', '0.0.0.0/0')], 'deny')],
            '20': [([('ipv4_dst', '10.0.2.0/24')], 'permit')],
        }
        self.router = RouterModel(
            'r', ports=['1', '2'], acls=self.acls,
            vlan_to_ports={'2': ['r.1_ingress'], 'nat_P': ('255.255.255.0', ['192.0.2.1', '192.0.2.2'])},
            vlan_to_acls={'2': ['in_10', 'out_20'], 'nat_P': ('inside', '20')},
            if_to_vlans={'1': [2]},
            routes=[([('ipv4_dst', '10.0.2.0/24')], ['r.2'])])

    def test_pre_routing_binds_the_configured_vlan(self):
        pre = {r.in_ports[0]: r for r in self.router.tables['r.pre_routing']}
        self.assertEqual(sorted(pre), ['r.1_ingress', 'r.2_ingress'])
        self.assertEqual(pre['r.1_ingress'].actions[0],
                         Rewrite([RuleField('packet.ether.vlan', '2'),
                                  RuleField('in_port', 'r.1_ingress')]))
        self.assertEqual(pre['r.2_ingress'].actions[0],
                         Rewrite([RuleField('in_port', 'r.2_ingress')]))

    def test_acls_land_per_direction_with_the_vlan_match(self):
        acl_in = [r for r in self.router.tables['r.acl_in'] if r.idx >= 32]
        self.assertEqual([r.idx for r in acl_in], [32, 33])
        self.assertEqual(_fields(acl_in[0]), [('packet.ether.vlan', '2'),
                                              ('packet.ipv4.source', '10.0.1.0/24')])
        self.assertEqual(acl_in[0].in_ports, ['r.1_ingress'])
        self.assertEqual(acl_in[0].actions, [Forward(['r.acl_in_out'])])
        self.assertEqual(acl_in[1].actions, [Forward([])])

        [acl_out] = self.router.tables['r.acl_out']
        self.assertEqual(acl_out.in_ports, ['r.acl_out_in'])
        self.assertEqual(acl_out.actions, [Forward(['r.acl_out_out'])])

    def test_nat_rewrites_the_source_to_each_pool_address(self):
        nat = [r for r in self.router.tables['r.acl_in']
               if any(isinstance(a, Rewrite) for a in r.actions)]
        self.assertEqual([r.actions[0] for r in nat],
                         [Rewrite([RuleField('packet.ipv4.source', ip)])
                          for ip in ('192.0.2.1', '192.0.2.2')])
        for rule in nat:
            self.assertEqual(rule.in_ports, ['r.acl_in_in'])
            self.assertEqual(_fields(rule), [('packet.ipv4.destination', '10.0.2.0/24')])
            self.assertEqual(rule.actions[1], Forward(['r.acl_in_out']))

    def test_routes_tag_the_egress_and_the_table_is_lpm(self):
        [route] = self.router.tables['r.routing']
        self.assertEqual(route.actions, [Rewrite([RuleField('out_port', 'r.2_egress')]),
                                         Forward(['r.routing_out'])])
        self.assertEqual(self.router.semantics_of('r.routing'), LPM)

    def test_port_naming(self):
        self.assertEqual(self.router.ingress_port('r.1'), 'r.1_ingress')
        self.assertEqual(self.router.egress_port('r.1'), 'r.1_egress')

    def test_json_round_trip(self):
        j = self.router.to_json()
        back = RouterModel.from_json(json.dumps(j))
        self.assertEqual(back.tables, self.router.tables)
        self.assertEqual(back.ports, self.router.ports)
        self.assertEqual(back.to_json()['tables'], j['tables'])

    def test_add_rules_turns_forwards_into_egress_tags(self):
        rule = Rule('r', 'x', 0, match=Match([RuleField('packet.ipv4.destination', '10.9.0.0/16')]),
                    actions=[Forward(['r.1']), Rewrite([RuleField('packet.ether.vlan', '3')])])
        self.router.add_rules([rule])
        self.assertEqual((rule.tid, rule.in_ports), ('r.routing', ['r.routing_in']))
        self.assertEqual(rule.actions, [
            Forward(['r.routing_out']),
            Rewrite([RuleField('out_port', 'r.1_egress'), RuleField('packet.ether.vlan', '3')]),
        ])
        self.assertEqual(self.router._adds['r.routing'], [rule])

    def test_remove_and_update_a_route(self):
        self.router.remove_rule(0)
        self.assertEqual(self.router._deletes, [0])
        self.assertEqual(self.router.tables['r.routing'], [])

        self.router.tables['r.routing'] = [Rule('r', 'r.routing', 0)]
        new = Rule('r', 'r.routing', 0, actions=[Forward(['r.2'])])
        self.router.update_rule(0, new)
        self.assertEqual(self.router._deletes, [0, 0])
        self.assertEqual(self.router._adds['r.routing'], [new])

    def test_diff_is_the_add_buffer(self):
        rule = Rule('r', 'x', 0, actions=[Forward(['r.1'])])
        self.router.add_rules([rule])
        diff = self.router - RouterModel('r', ports=['1', '2'])
        self.assertIsInstance(diff, RouterModel)
        self.assertEqual(diff.tables['r.routing'], [rule])


class TestParseCiscoInterfacesNat(unittest.TestCase):
    """ The interface parser's NAT pool and NAT source lines, its comments and
    the switchport lines it skips; and the host netmask. """

    def test_nat_and_skipped_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'interfaces.txt')
            with open(path, 'w', encoding='utf-8') as out:
                out.write("\n".join([
                    "# a comment",
                    "",
                    "interface Gi1",
                    " switchport",
                    " switchport mode trunk",
                    " switchport trunk encapsulation dot1q",
                    " switchport trunk allowed vlan 3,4",
                    "ip nat pool P 192.0.2.1 192.0.2.2 netmask 255.255.255.0",
                    "ip nat inside source list 20 pool P",
                    "hostname r",
                ]) + "\n")
            domain, ports, ips, acls, if_to_vlans = parse_cisco_interfaces(path)
        self.assertEqual((domain, ips), ({}, {}))
        self.assertEqual(ports, {'nat_P': ('255.255.255.0', ['192.0.2.1', '192.0.2.2'])})
        self.assertEqual(acls, {'nat_P': ('inside', '20')})
        self.assertEqual(if_to_vlans, {'Gi1': [3, 4]})

    def test_a_host_netmask_is_a_host_prefix(self):
        self.assertEqual(
            _build_cidr('192.0.2.1', '255.255.255.255', '4', inverse_netmask=True),
            '192.0.2.1/32')


class TestParseCiscoAclsSixTokens(unittest.TestCase):
    """ `access-list <id> <action> <proto> <src> <dst>` has no masks; both
    addresses take the all-ones wildcard. """

    def test_six_token_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'acls.txt')
            with open(path, 'w', encoding='utf-8') as out:
                out.write("access-list 100 deny ip any any\n")
            acls = parse_cisco_acls(path)
        self.assertEqual(acls, {'100': [([('ipv4_src', '0.0.0.0/0'),
                                          ('ipv4_dst', '0.0.0.0/0')], 'deny')]})


if __name__ == '__main__':
    unittest.main()
