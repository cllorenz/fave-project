#!/usr/bin/env python2

""" This module provides tests for router models.
"""

import unittest

from netplumber.model import Model
from netplumber.mapping import Mapping
from topology.router import RouterModel
from ip6np.packet_filter import PacketFilterModel
from openflow.switch import SwitchModel, Forward, Rewrite, SwitchRule
from openflow.switch import Match, SwitchRuleField
from util.match_util import OXM_FIELD_TO_MATCH_FIELD


class TestRouterModel(unittest.TestCase):
    """ This class provides tests for the router model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = RouterModel("foo")


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a router model to JSON.
        """

        self.assertEqual(
            self.model.to_json(),
            {
                'mapping': {'in_port': 0, 'length': 64, 'out_port': 32},
                'node': 'foo',
                'ports': {
                    'acl_in_in': 2,
                    'acl_in_out': 3,
                    'acl_out_in': 6,
                    'acl_out_out': 7,
                    'in_1': 9,
                    'out_2': 11,
                    'post_routing_in': 8,
                    'pre_routing_out': 1,
                    'routing_in': 4,
                    'routing_out': 5
                },
                'private_ports' : 8,
                'tables': {
                    'acl_in': [{
                        'actions': [],
                        'idx': 1,
                        'in_ports': ['in'],
                        'mapping': {
                            'length': 48,
                            'packet.ether.vlan': 0,
                            'packet.ipv4.source': 16
                        },
                        'match': {'fields': [{
                            'name': 'packet.ether.vlan',
                            'value': '4095'
                        }, {
                            'name': 'packet.ipv4.source',
                            'value': '192.168.0.0/16'
                        }]},
                        'node': 'foo',
                        'tid': 'acl_in'
                    }, {
                        'actions': [],
                        'idx': 2,
                        'in_ports': ['in'],
                        'mapping': {
                            'length': 48,
                            'packet.ether.vlan': 0,
                            'packet.ipv4.source': 16
                        },
                        'match': {'fields': [{
                            'name': 'packet.ether.vlan',
                            'value': '4095'
                        }, {
                            'name': 'packet.ipv4.source',
                            'value': '10.0.0.0/8'
                        }]},
                        'node': 'foo',
                        'tid': 'acl_in'
                    }],
                    'acl_out': [],
                    'post_routing': [{
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
                            }, {
                                'name': 'out_port',
                                'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
                            }]
                        }, {
                            'name': 'forward',
                            'ports': ['foo_2']
                        }],
                        'idx': 2,
                        'in_ports': ['in'],
                        'mapping': {'length': 64, 'out_port': 0, 'in_port': 32},
                        'match': {'fields': [{
                            'name': 'out_port',
                            'value': 'foo.2'
                        }]},
                        'node': 'foo',
                        'tid': 'post_routing'
                    }, {
                        'actions': [],
                        'idx': 0,
                        'in_ports': ['in'],
                        'mapping': {
                            'in_port': 0,
                            'length': 64,
                            'out_port': 32
                        },
                        'match': {
                            'fields': [{
                                'name': 'in_port',
                                'value': 'foo.1'
                            }, {
                                'name': 'out_port',
                                'value': 'foo.2'
                        }]},
                        'node': 'foo',
                        'tid': 'post_routing'
                    }],
                    'pre_routing': [{
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'foo.1'
                            }]}, {
                                'name': 'forward',
                                'ports': ['foo_pre_routing_out']
                            }
                        ],
                        'idx': 0,
                        'in_ports': ['foo.1'],
                        'mapping': {'length': 32, 'in_port' : 0},
                        'match': None,
                        'node': 'foo',
                        'tid': 'pre_routing'
                    }],
                    'routing': []
                },
                'type': 'router',
                'wiring': [
                    ('pre_routing_out', 'acl_in_in'),
                    ('acl_in_out', 'routing_in'),
                    ('routing_out', 'acl_out_in'),
                    ('acl_out_out', 'post_routing_in')
                ]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a router model from JSON.
        """

        router = RouterModel.from_json({
            'mapping': {'in_port': 0, 'length': 64, 'out_port': 32},
            'node': 'foo',
            'ports': {
                'acl_in_in': 2,
                'acl_in_out': 3,
                'acl_out_in': 6,
                'acl_out_out': 7,
                'in_1': 9,
                'out_2': 11,
                'post_routing_in': 8,
                'pre_routing_out': 1,
                'routing_in': 4,
                'routing_out': 5
            },
            'private_ports' : 8,
            'tables': {
                'acl_in': [{
                    'actions': [],
                    'idx': 1,
                    'in_ports': ['in'],
                    'mapping': {
                        'length': 48,
                        'packet.ether.vlan': 0,
                        'packet.ipv4.source': 16
                    },
                    'match': {'fields': [{
                        'name': 'packet.ether.vlan',
                        'value': '4095'
                    }, {
                        'name': 'packet.ipv4.source',
                        'value': '192.168.0.0/16'
                    }]},
                    'node': 'foo',
                    'tid': 'acl_in'
                }, {
                    'actions': [],
                    'idx': 2,
                    'in_ports': ['in'],
                    'mapping': {
                        'length': 48,
                        'packet.ether.vlan': 0,
                        'packet.ipv4.source': 16
                    },
                    'match': {'fields': [{
                        'name': 'packet.ether.vlan',
                        'value': '4095'
                    }, {
                        'name': 'packet.ipv4.source',
                        'value': '10.0.0.0/8'
                    }]},
                    'node': 'foo',
                    'tid': 'acl_in'
                }],
                'acl_out': [],
                'post_routing': [{
                    'actions': [{
                        'name': 'rewrite',
                        'rw': [{
                            'name': 'in_port',
                            'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
                        }, {
                            'name': 'out_port',
                            'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
                        }]
                    }, {
                        'name': 'forward',
                        'ports': ['foo_2']
                    }],
                    'idx': 2,
                    'in_ports': ['in'],
                    'mapping': {'length': 32, 'out_port': 0},
                    'match': {'fields': [{
                        'name': 'out_port',
                        'value': 'foo.2'
                    }]},
                    'node': 'foo',
                    'tid': 'post_routing'
                }, {
                    'actions': [],
                    'idx': 0,
                    'in_ports': ['in'],
                    'mapping': {
                        'in_port': 0,
                        'length': 64,
                        'out_port': 32
                    },
                    'match': {
                        'fields': [{
                            'name': 'in_port',
                            'value': 'foo.1'
                        }, {
                            'name': 'out_port',
                            'value': 'foo.2'
                    }]},
                    'node': 'foo',
                    'tid': 'post_routing'
                }],
                'pre_routing': [{
                    'actions': [{
                        'name': 'rewrite',
                        'rw': [{
                            'name': 'in_port',
                            'value': 'foo.1'
                        }]}, {
                            'name': 'forward',
                            'ports': ['foo_pre_routing_out']
                        }
                    ],
                    'idx': 0,
                    'in_ports': ['foo.1'],
                    'mapping': {'length': 0},
                    'match': None,
                    'node': 'foo',
                    'tid': 'pre_routing'
                }],
                'routing': []
            },
            'type': 'router',
            'wiring': [
                ('pre_routing_out', 'acl_in_in'),
                ('acl_in_out', 'routing_in'),
                ('routing_out', 'acl_out_in'),
                ('acl_out_out', 'post_routing_in')
            ]
        })

        self.assertEqual(
            router,
            self.model
        )


    def test_complex(self):
        """ Tests the a more complex model.
        """

        ports = {'1' : 1, '2' : 2}
        acls = {
            'acl_2' : [([('ipv6_dst', "2001:db8::1")], "permit")],
            'acl_deny' : [([], "deny")]
        }
        routes = [([('ipv6_dst', '2001:db8::0/32')], [1]), ([], [2])]

        vlan_to_ports = {"2" : [1, 2], "1" : []}
        vlan_to_acls = {"2" : ['in_acl_2'], "1" : ['out_acl_deny']}

        router1 = RouterModel(
            "foo",
            ports=ports,
            acls=acls,
            routes=routes,
            vlan_to_ports=vlan_to_ports,
            vlan_to_acls=vlan_to_acls
        )

        router2 = RouterModel.from_json(router1.to_json())

        self.assertEqual(router1, router2)


class TestGenericModel(unittest.TestCase):
    """ This class provides tests for the generic model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = Model("foo")


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a generic model to JSON.
        """

        self.assertEqual(
            self.model.to_json(),
            {
                'mapping': {'length':0},
                'node': 'foo',
                'ports': {},
                'private_ports' : 0,
                'tables': {},
                'type': 'model',
                'wiring': []
            }
        )


    def test_from_json(self):
        """ Tests the creation of a generic model from JSON.
        """

        self.assertEqual(
            Model.from_json({
                'mapping': {'length':0},
                'node': 'foo',
                'ports': {},
                'tables': {},
                'type': 'model',
                'wiring': []
            }),
            self.model
        )

    def test_complex(self):
        """ Tests the a more complex model.
        """

        tables = {"t1":[], "t2":[]}
        ports = {'1' : 3, '2' : 4, 't1_out' : 1, 't2_in' : 2}
        wiring = [('t1_out', 't2_in')]

        model1 = Model(
            "foo",
            tables=tables,
            ports=ports,
            wiring=wiring
        )

        model2 = Model.from_json(model1.to_json())

        self.assertEqual(model1, model2)


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
                'mapping': {'length': 0},
                'node': 'foo',
                'ports': {
                    'forward_rules_accept': 12,
                    'forward_rules_in': 11,
                    'forward_states_accept': 9,
                    'forward_states_in': 8,
                    'forward_states_miss': 10,
                    'in_1': 23,
                    'input_rules_accept': 7,
                    'input_rules_in': 6,
                    'input_states_accept': 4,
                    'input_states_in': 3,
                    'input_states_miss': 5,
                    'internals_in': 18,
                    'internals_out': 19,
                    'out_2': 26,
                    'output_rules_accept': 17,
                    'output_rules_in': 16,
                    'output_states_accept': 14,
                    'output_states_in': 13,
                    'output_states_miss': 15,
                    'post_routing_in': 20,
                    'pre_routing_forward': 2,
                    'pre_routing_input': 1
                },
                'private_ports': 20,
                'tables': {
                    'forward_rules': [],
                    'forward_states': [
                        {
                            'actions': [
                                {
                                    'name': 'forward',
                                    'ports': ['foo_forward_states_miss']
                                }
                            ],
                            'idx': 65535,
                            'in_ports': ['foo_forward_states_in'],
                            'mapping': {'length': 0},
                            'match': None,
                            'node': 'foo',
                            'tid': 'foo_forward_states'
                        }
                    ],
                    'input_rules': [],
                    'input_states': [
                        {
                            'actions': [
                                {
                                    'name': 'forward',
                                    'ports': ['foo_input_states_miss']
                                }
                            ],
                            'idx': 65535,
                            'in_ports': ['foo_input_states_in'],
                            'mapping': {'length': 0},
                            'match': None,
                            'node': 'foo',
                            'tid': 'foo_input_states'
                        }
                    ],
                    'internals': [],
                    'output_rules': [],
                    'output_states': [
                        {
                            'actions': [
                                {
                                    'name': 'forward',
                                    'ports': ['foo_output_states_miss']
                                }
                            ],
                            'idx': 65535,
                            'in_ports': ['foo_output_states_in'],
                            'mapping': {'length': 0},
                            'match': None,
                            'node': 'foo',
                            'tid': 'foo_output_states'
                        }
                    ],
                    'post_routing': [],
                    'pre_routing': []
                },
                'type': 'packet_filter',
                'wiring': [
                    ('pre_routing_input', 'input_states_in'),
                    ('input_states_accept', 'internals_in'),
                    ('input_states_miss', 'input_rules_in'),
                    ('input_rules_accept', 'internals_in'),
                    ('pre_routing_forward', 'forward_states_in'),
                    ('forward_states_accept', 'post_routing_in'),
                    ('forward_states_miss', 'forward_rules_in'),
                    ('forward_rules_accept', 'post_routing_in'),
                    ('internals_out', 'output_states_in'),
                    ('output_states_accept', 'post_routing_in'),
                    ('output_states_miss', 'output_rules_in'),
                    ('output_rules_accept', 'post_routing_in')
                ]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a packet filter model from JSON.
        """

        self.assertEqual(
            PacketFilterModel.from_json({
                'mapping': {'length': 0},
                'node': 'foo',
                'ports': {
                    'forward_rules_accept': 12,
                    'forward_rules_in': 11,
                    'forward_states_accept': 9,
                    'forward_states_in': 8,
                    'forward_states_miss': 10,
                    'in_1': 23,
                    'input_rules_accept': 7,
                    'input_rules_in': 6,
                    'input_states_accept': 4,
                    'input_states_in': 3,
                    'input_states_miss': 5,
                    'internals_in': 18,
                    'internals_out': 19,
                    'out_2': 26,
                    'output_rules_accept': 17,
                    'output_rules_in': 16,
                    'output_states_accept': 14,
                    'output_states_in': 13,
                    'output_states_miss': 15,
                    'post_routing_in': 20,
                    'pre_routing_forward': 2,
                    'pre_routing_input': 1
                },
                'internal_ports': 20,
                'tables': {
                    'forward_rules': [],
                    'forward_states': [
                        {
                            'actions': [
                                {
                                    'name': 'forward',
                                    'ports': ['foo_forward_states_miss']
                                }
                            ],
                            'idx': 65535,
                            'in_ports': ['foo_forward_states_in'],
                            'mapping': {'length': 0},
                            'match': None,
                            'node': 'foo',
                            'tid': 'foo_forward_states'
                        }
                    ],
                    'input_rules': [],
                    'input_states': [
                        {
                            'actions': [
                                {
                                    'name': 'forward',
                                    'ports': ['foo_input_states_miss']
                                }
                            ],
                            'idx': 65535,
                            'in_ports': ['foo_input_states_in'],
                            'mapping': {'length': 0},
                            'match': None,
                            'node': 'foo',
                            'tid': 'foo_input_states'
                        }
                    ],
                    'internals': [],
                    'output_rules': [],
                    'output_states': [
                        {
                            'actions': [
                                {
                                    'name': 'forward',
                                    'ports': ['foo_output_states_miss']
                                }
                            ],
                            'idx': 65535,
                            'in_ports': ['foo_output_states_in'],
                            'mapping': {'length': 0},
                            'match': None,
                            'node': 'foo',
                            'tid': 'foo_output_states'
                        }
                    ],
                    'post_routing': [],
                    'pre_routing': []
                },
                'type': 'packet_filter',
                'wiring': [
                    ('pre_routing_input', 'input_states_in'),
                    ('input_states_accept', 'internals_in'),
                    ('input_states_miss', 'input_rules_in'),
                    ('input_rules_accept', 'internals_in'),
                    ('pre_routing_forward', 'forward_states_in'),
                    ('forward_states_accept', 'post_routing_in'),
                    ('forward_states_miss', 'forward_rules_in'),
                    ('forward_rules_accept', 'post_routing_in'),
                    ('internals_out', 'output_states_in'),
                    ('output_states_accept', 'post_routing_in'),
                    ('output_states_miss', 'output_rules_in'),
                    ('output_rules_accept', 'post_routing_in')
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
                'mapping': {},
                'node': 'foo',
                'ports': {},
                'private_ports': 0,
                'rules': [],
                'tables': {"1" : []},
                'type': 'switch',
                'wiring': []
            }
        )


    def test_from_json(self):
        """ Tests the creation of a switch model from JSON.
        """

        self.assertEqual(
            SwitchModel.from_json({
                'mapping': {},
                'node': 'foo',
                'ports': {},
                'private_ports': 0,
                'rules': [],
                'tables': {"1" : []},
                'type': 'switch',
                'wiring': []
            }),
            self.model
        )


    def test_complex(self):
        """ Tests the a more complex model.
        """

        ports = {'1' : 1, '2' : 2, '3' : 3, '4' : 4}

        model1 = SwitchModel(
            "foo",
            ports=ports
        )

        model1.add_rule(65535, SwitchRule("foo", 1, 65535, actions=[]))

        match1 = Match(fields=[SwitchRuleField(
            OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:1::0/48"
        )])
        actions1 = [Forward([3])]
        mapping = Mapping()
        mapping.extend(OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"])
        model1.add_rule(
            0,
            SwitchRule(
                "foo", 1, 0,
                in_ports=[1, 2],
                match=match1,
                actions=actions1,
                mapping=mapping
            )
        )

        match2 = Match(fields=[SwitchRuleField(
            OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:2::0/48"
        )])
        actions2 = [
            Rewrite([SwitchRuleField(
                OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:3::0/48"
            )]),
            Forward([4])
        ]
        model1.add_rule(
            1,
            SwitchRule(
                "foo", 1, 1,
                in_ports=[1, 2, 3],
                match=match2,
                actions=actions2,
                mapping=mapping
            )
        )

        model2 = SwitchModel.from_json(model1.to_json())

        self.assertEqual(model1, model2)



if __name__ == '__main__':
    unittest.main()
