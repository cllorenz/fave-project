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

""" This module provides tests for router models.
"""

import unittest
import tempfile

from iptables.generator import generate
from iptables.parser import IP6TablesParser
from devices.packet_filter import PacketFilterModel
from devices.switch import SwitchModel
from rule.rule_model import Forward, Rewrite, Rule, Match, RuleField
from util.model_util import TABLE_MAX
from util.match_util import OXM_FIELD_TO_MATCH_FIELD


class TestPacketFilterModel(unittest.TestCase):
    """ This class provides tests for the packet filter model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = PacketFilterModel("foo")


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a packet filter model to JSON.
        """

        self.assertEqual(
            self.model.to_json(),
            {
                'node': 'foo',
                'ports': {
                    "foo.pre_routing_input" : "foo.pre_routing",
                    "foo.pre_routing_forward" : "foo.pre_routing",
                    "foo.input_filter_in" : "foo.input_filter",
                    "foo.input_filter_accept" : "foo.input_filter",
                    "foo.forward_filter_in" : "foo.forward_filter",
                    "foo.forward_filter_accept" : "foo.forward_filter",
                    "foo.output_filter_in" : "foo.output_filter",
                    "foo.output_filter_accept" : "foo.output_filter",
                    "foo.internals_in" : "foo.internals",
                    "foo.internals_out" : "foo.internals",
                    "foo.post_routing_in" : "foo.post_routing",
                    "foo.routing_in" : "foo.routing",
                    "foo.routing_out" : "foo.routing",
                    'foo.1': '',
                    'foo.2': '',
                    'foo.1_ingress': 'foo.pre_routing',
                    'foo.2_ingress': 'foo.pre_routing',
                    'foo.1_egress': 'foo.post_routing',
                    'foo.2_egress': 'foo.post_routing'
                },
                'tables': {
                    'foo.forward_filter': [],
                    'foo.input_filter': [],
                    'foo.internals': [],
                    'foo.output_filter': [],
                    'foo.post_routing': [
                        {
                            'actions': [{
                                'name': 'rewrite',
                                'rw': [{
                                    'name': 'in_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }]
                            }, {
                                'name': 'forward',
                                'ports': ['foo.1_egress']
                            }],
                            'idx': 2,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'out_port',
                                    'value': 'foo.1_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }, {
                            'actions': [{
                                'name': 'rewrite',
                                'rw': [{
                                    'name': 'in_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }]
                            }, {
                                'name': 'forward',
                                'ports': ['foo.2_egress']
                            }],
                            'idx': 3,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'out_port',
                                    'value': 'foo.2_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }, {
                            'actions': [],
                            'idx': 0,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'in_port',
                                    'value': 'foo.1_ingress',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'foo.1_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }, {
                            'actions': [],
                            'idx': 1,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'in_port',
                                    'value': 'foo.2_ingress',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'foo.2_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }
                    ],
                    'foo.pre_routing': [],
                    'foo.routing' : []
                },
                'type': 'packet_filter',
                'wiring': [
                    ("foo.pre_routing_input", "foo.input_filter_in"),
                    ("foo.input_filter_accept", "foo.internals_in"),
                    ("foo.pre_routing_forward", "foo.forward_filter_in"),
                    ("foo.forward_filter_accept", "foo.routing_in"),
                    ("foo.internals_out", "foo.output_filter_in"),
                    ("foo.output_filter_accept", "foo.routing_in"),
                    ("foo.routing_out", "foo.post_routing_in")
                ]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a packet filter model from JSON.
        """

        self.assertEqual(
            PacketFilterModel.from_json({
                'node': 'foo',
                'ports': {
                    "foo.pre_routing_input" : "foo.pre_routing",
                    "foo.pre_routing_forward" : "foo.pre_routing",
                    "foo.input_filter_in" : "foo.input_filter",
                    "foo.input_filter_accept" : "foo.input_filter",
                    "foo.forward_filter_in" : "foo.forward_filter",
                    "foo.forward_filter_accept" : "foo.forward_filter",
                    "foo.output_filter_in" : "foo.output_filter",
                    "foo.output_filter_accept" : "foo.output_filter",
                    "foo.internals_in" : "foo.internals",
                    "foo.internals_out" : "foo.internals",
                    "foo.post_routing_in" : "foo.post_routing",
                    "foo.routing_in" : "foo.routing",
                    "foo.routing_out" : "foo.routing",
                    'foo.1': '',
                    'foo.2': '',
                    'foo.1_ingress': 'foo.pre_routing',
                    'foo.2_ingress': 'foo.pre_routing',
                    'foo.1_egress': 'foo.post_routing',
                    'foo.2_egress': 'foo.post_routing'
                },
                'tables': {
                    'foo.forward_filter': [],
                    'foo.input_filter': [],
                    'foo.internals': [],
                    'foo.output_filter': [],
                    'foo.post_routing': [
                        {
                            'actions': [{
                                'name': 'rewrite',
                                'rw': [{
                                    'name': 'in_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }]
                            }, {
                                'name': 'forward',
                                'ports': ['foo.1_egress']
                            }],
                            'idx': 2,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'out_port',
                                    'value': 'foo.1_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }, {
                            'actions': [{
                                'name': 'rewrite',
                                'rw': [{
                                    'name': 'in_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                    'negated' : False
                                }]
                            }, {
                                'name': 'forward',
                                'ports': ['foo.2_egress']
                            }],
                            'idx': 3,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'out_port',
                                    'value': 'foo.2_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }, {
                            'actions': [],
                            'idx': 0,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'in_port',
                                    'value': 'foo.1_ingress',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'foo.1_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }, {
                            'actions': [],
                            'idx': 1,
                            'in_ports': ['foo.post_routing_in'],
                            'match': {
                                'fields': [{
                                    'name': 'in_port',
                                    'value': 'foo.2_ingress',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'foo.2_egress',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }
                    ],
                    'foo.pre_routing': [],
                    'foo.routing' : []
                },
                'type': 'packet_filter',
                'wiring': [
                    ("foo.pre_routing_input", "foo.input_filter_in"),
                    ("foo.input_filter_accept", "foo.internals_in"),
                    ("foo.pre_routing_forward", "foo.forward_filter_in"),
                    ("foo.forward_filter_accept", "foo.routing_in"),
                    ("foo.internals_out", "foo.output_filter_in"),
                    ("foo.output_filter_accept", "foo.routing_in"),
                    ("foo.routing_out", "foo.post_routing_in")
                ]
            }),
            self.model
        )


class TestSwitchModel(unittest.TestCase):
    """ This class provides tests for the switch model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = SwitchModel("foo")


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a switch model to JSON.
        """

        self.assertEqual(
            self.model.to_json(),
            {
                'node': 'foo',
                'ports': {},
                'tables': {"foo.1" : []},
                'type': 'switch',
                'wiring': []
            }
        )


    def test_from_json(self):
        """ Tests the creation of a switch model from JSON.
        """

        self.assertEqual(
            SwitchModel.from_json({
                'node': 'foo',
                'ports': {},
                'tables': {"foo.1" : []},
                'type': 'switch',
                'wiring': []
            }),
            self.model
        )


    def test_complex(self):
        """ Tests the a more complex model.
        """

        ports = ['1', '2', '3', '4']

        model1 = SwitchModel(
            "foo",
            ports=ports
        )

        model1.add_rule(Rule("foo", 1, TABLE_MAX, actions=[]))

        match1 = Match(fields=[RuleField(
            OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:1::0/48"
        )])
        actions1 = [Forward(['foo.1'])]
        model1.add_rule(
            Rule(
                "foo", 1, 0,
                in_ports=['foo.1', 'foo.2'],
                match=match1,
                actions=actions1
            )
        )

        match2 = Match(fields=[RuleField(
            OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:2::0/48"
        )])
        actions2 = [
            Rewrite([RuleField(
                OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:3::0/48"
            )]),
            Forward(['foo.4'])
        ]
        model1.add_rule(
            Rule(
                "foo", 1, 1,
                in_ports=['foo.1', 'foo.2', 'foo.3'],
                match=match2,
                actions=actions2
            )
        )

        model2 = SwitchModel.from_json(model1.to_json())

        self.assertEqual(model1, model2)


class TestPacketFilterGenerator(unittest.TestCase):
    """ This class provides tests for the packet filter generator.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = PacketFilterModel("foo")


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_forward_filter(self):
        """ Tests whether a simple forward rule set is correctly modeled in a
            packet filter.
        """
        iptables = '\n'.join([
            'ip6tables -P FORWARD DROP',
            'ip6tables -P INPUT DROP',
            'ip6tables -P OUTPUT DROP',
            'ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT',
            'ip6tables -A FORWARD -d 2001:db8::0/64 -p tcp --dport 80 -j ACCEPT'
        ])

        node = 'foo'
        address = '2001:db8::1'
        ports = ['1', '2']

        self.model.set_address(address)
        self.model.tables['foo.input_filter'] = [
            Rule(
                node,
                'foo.input_filter',
                0,
                in_ports=['foo.input_filter_in'],
                match=Match([]),
                actions=[]
            )
        ]
        self.model.tables['foo.output_filter'] = [
            Rule(
                node,
                'foo.output_filter',
                0,
                in_ports=['foo.output_filter_in'],
                match=Match([]),
                actions=[]
            )
        ]
        self.model.tables['foo.forward_filter'] = [
            Rule(
                node,
                'foo.forward_filter',
                0,
                in_ports=['foo.forward_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.proto', '6'),
                    RuleField('packet.ipv6.source', '2001:db8:0:0:0:0:0:0/64'),
                    RuleField('packet.upper.sport', '80'),
                    RuleField('related', '1')
                ]),
                actions=[Forward(['foo.forward_filter_accept'])]
            ),
            Rule(
                node,
                'foo.forward_filter',
                1,
                in_ports=['foo.forward_filter_in'],
                match=Match([RuleField('related', '1')]),
                actions=[]
            ),
            Rule(
                node,
                'foo.forward_filter',
                2,
                in_ports=['foo.forward_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.destination', '2001:db8::0/64'),
                    RuleField('packet.ipv6.proto', 'tcp'),
                    RuleField('packet.upper.dport', '80')
                ]),
                actions=[Forward(['foo.forward_filter_accept'])]
            ),
            Rule(
                node,
                'foo.forward_filter',
                3,
                in_ports=['foo.forward_filter_in'],
                match=Match([]),
                actions=[]
            )
        ]

        _fd, iptables_file = tempfile.mkstemp()
        with open(iptables_file, 'w') as tmp_file:
            tmp_file.write(iptables + '\n')
        parser = IP6TablesParser()
        ast = parser.parse(iptables_file)
        result = generate(ast, node, address, ports)

        self.assertEqual(result.to_json(), self.model.to_json())


    def test_input_output_filters(self):
        """ Tests whether a simple input/output rule set is correctly modeled
            in a packet filter.
        """
        iptables = '\n'.join([
            'ip6tables -P FORWARD DROP',
            'ip6tables -P INPUT DROP',
            'ip6tables -P OUTPUT DROP',
            'ip6tables -A OUTPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT',
            'ip6tables -A OUTPUT -d 2001:db8:abc:1::6 -p tcp --dport 53 -j ACCEPT',
            'ip6tables -A OUTPUT -d 2001:db8:abc:1::0/64 -j DROP',
            'ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT',
            'ip6tables -A INPUT -s 2001:db8:abc:1::0/64 -j DROP',
            'ip6tables -A INPUT -d 2001:db8:abc::0/64 -p tcp --dport 22 -j ACCEPT'
        ])


        node = 'foo'
        address = '2001:db8::1'
        ports = ['1', '2']

        self.model.set_address(address)
        self.model.tables['foo.input_filter'] = [
            Rule(
                node,
                'foo.input_filter',
                0,
                in_ports=['foo.input_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.proto', '6'),
                    RuleField('packet.ipv6.source', '2001:db8:abc:1:0:0:0:6'),
                    RuleField('packet.upper.sport', '53'),
                    RuleField('related', '1')
                ]),
                actions=[Forward(['foo.input_filter_accept'])]
            ),
            Rule(
                node,
                'foo.input_filter',
                1,
                in_ports=['foo.input_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.source', '2001:db8:abc:1:0:0:0:0/64'),
                    RuleField('related', '1')
                ]),
                actions=[]
            ),
            Rule(
                node,
                'foo.input_filter',
                2,
                in_ports=['foo.input_filter_in'],
                match=Match([RuleField('related', '1')]),
                actions=[]
            ),
            Rule(
                node,
                'foo.input_filter',
                3,
                in_ports=['foo.input_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.source', '2001:db8:abc:1::0/64')
                ]),
                actions=[]
            ),
            Rule(
                node,
                'foo.input_filter',
                4,
                in_ports=['foo.input_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.destination', '2001:db8:abc::0/64'),
                    RuleField('packet.ipv6.proto', 'tcp'),
                    RuleField('packet.upper.dport', '22')
                ]),
                actions=[Forward(['foo.input_filter_accept'])]
            ),
            Rule(
                node,
                'foo.input_filter',
                5,
                in_ports=['foo.input_filter_in'],
                match=Match([]),
                actions=[]
            )
        ]
        self.model.tables['foo.output_filter'] = [
            Rule(
                node,
                'foo.output_filter',
                0,
                in_ports=['foo.output_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.destination', '2001:db8:abc:1:0:0:0:0/64'),
                    RuleField('related', '1')
                ]),
                actions=[]
            ),
            Rule(
                node,
                'foo.output_filter',
                1,
                in_ports=['foo.output_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.proto', '6'),
                    RuleField('packet.ipv6.source', '2001:db8:abc:0:0:0:0:0/64'),
                    RuleField('packet.upper.sport', '22'),
                    RuleField('related', '1')
                ]),
                actions=[Forward(['foo.output_filter_accept'])]
            ),
            Rule(
                node,
                'foo.output_filter',
                2,
                in_ports=['foo.output_filter_in'],
                match=Match([RuleField('related', '1')]),
                actions=[]
            ),
            Rule(
                node,
                'foo.output_filter',
                3,
                in_ports=['foo.output_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.destination', '2001:db8:abc:1::6'),
                    RuleField('packet.ipv6.proto', 'tcp'),
                    RuleField('packet.upper.dport', '53')
                ]),
                actions=[Forward(['foo.output_filter_accept'])]
            ),
            Rule(
                node,
                'foo.output_filter',
                4,
                in_ports=['foo.output_filter_in'],
                match=Match([
                    RuleField('packet.ipv6.destination', '2001:db8:abc:1::0/64')
                ]),
                actions=[]
            ),
            Rule(
                node,
                'foo.output_filter',
                5,
                in_ports=['foo.output_filter_in'],
                match=Match([]),
                actions=[]
            )
        ]
        self.model.tables['foo.forward_filter'] = [
            Rule(
                node,
                'foo.forward_filter',
                0,
                in_ports=['foo.forward_filter_in'],
                match=Match([]),
                actions=[]
            )
        ]

        _fd, iptables_file = tempfile.mkstemp()
        with open(iptables_file, 'w') as tmp_file:
            tmp_file.write(iptables + '\n')
        parser = IP6TablesParser()
        ast = parser.parse(iptables_file)
        result = generate(ast, node, address, ports)

        self.assertEqual(result, self.model)


if __name__ == '__main__':
    unittest.main()
