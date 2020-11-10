#!/usr/bin/env python2

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
                            'value': '4095',
                            'negated' : False
                        }, {
                            'name': 'packet.ipv4.source',
                            'value': '192.168.0.0/16',
                            'negated' : False
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
                            'value': '4095',
                            'negated' : False
                        }, {
                            'name': 'packet.ipv4.source',
                            'value': '10.0.0.0/8',
                            'negated' : False
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
                                'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                'negated' : False
                            }, {
                                'name': 'out_port',
                                'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                                'negated' : False
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
                            'value': 'foo.2',
                            'negated' : False
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
                                'value': 'foo.1',
                                'negated' : False
                            }, {
                                'name': 'out_port',
                                'value': 'foo.2',
                                'negated' : False
                        }]},
                        'node': 'foo',
                        'tid': 'post_routing'
                    }],
                    'pre_routing': [{
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'foo.1',
                                'negated' : False
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
                        'value': '4095',
                        'negated' : False
                    }, {
                        'name': 'packet.ipv4.source',
                        'value': '192.168.0.0/16',
                        'negated' : False
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
                        'value': '4095',
                        'negated' : False
                    }, {
                        'name': 'packet.ipv4.source',
                        'value': '10.0.0.0/8',
                        'negated' : False
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
                            'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                            'negated' : False
                        }, {
                            'name': 'out_port',
                            'value': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                            'negated' : False
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
                        'value': 'foo.2',
                        'negated' : False
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
                            'value': 'foo.1',
                            'negated' : False
                        }, {
                            'name': 'out_port',
                            'value': 'foo.2',
                            'negated' : False
                    }]},
                    'node': 'foo',
                    'tid': 'post_routing'
                }],
                'pre_routing': [{
                    'actions': [{
                        'name': 'rewrite',
                        'rw': [{
                            'name': 'in_port',
                            'value': 'foo.1',
                            'negated' : False
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

        self.maxDiff = None

        self.assertEqual(
            self.model.to_json(),
            {
                'mapping': {'length': 64, 'out_port': 0, 'in_port': 32},
                'node': 'foo',
                'ports': {
                    "pre_routing_input" : 1,
                    "pre_routing_forward" : 2,
                    "input_filter_in" : 3,
                    "input_filter_accept" : 4,
                    "forward_filter_in" : 5,
                    "forward_filter_accept" : 6,
                    "output_filter_in" : 7,
                    "output_filter_accept" : 8,
                    "internals_in" : 9,
                    "internals_out" : 10,
                    "post_routing_in" : 11,
                    "routing_in" : 12,
                    "routing_out" : 13,
                    'in_1': 16,
                    'out_2': 19
                },
                'private_ports': 13,
                'tables': {
                    'forward_filter': [],
                    'input_filter': [],
                    'internals': [],
                    'output_filter': [],
                    'post_routing': [
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
                                    }
                                ]
                            }, {
                                'name': 'forward',
                                'ports': ['foo_2']
                            }],
                            'idx': 2,
                            'in_ports': ['in'],
                            'mapping': {
                                'in_port': 32,
                                'length': 64,
                                'out_port': 0
                            },
                            'match': {
                                'fields': [{
                                    'name': 'out_port',
                                    'value': 'foo.2',
                                    'negated' : False
                                }]
                            },
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
                                    'value': 'foo.1',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'foo.2',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }
                    ],
                    'pre_routing': [],
                    'routing' : []
                },
                'type': 'packet_filter',
                'wiring': [
                    ("pre_routing_input", "input_filter_in"),
                    ("input_filter_accept", "internals_in"),
                    ("pre_routing_forward", "forward_filter_in"),
                    ("forward_filter_accept", "routing_in"),
                    ("internals_out", "output_filter_in"),
                    ("output_filter_accept", "routing_in"),
                    ("routing_out", "post_routing_in")
                ]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a packet filter model from JSON.
        """

        self.assertEqual(
            PacketFilterModel.from_json({
                'mapping': {'length': 64, 'out_port': 0, 'in_port': 32},
                'node': 'foo',
                'ports': {
                    "pre_routing_input" : 1,
                    "pre_routing_forward" : 2,
                    "input_filter_in" : 3,
                    "input_filter_accept" : 4,
                    "forward_filter_in" : 5,
                    "forward_filter_accept" : 6,
                    "output_filter_in" : 7,
                    "output_filter_accept" : 8,
                    "internals_in" : 9,
                    "internals_out" : 10,
                    "post_routing_in" : 11,
                    "routing_in" : 12,
                    "routing_out" : 13,
                    'in_1': 16,
                    'out_2': 19
                },
                'private_ports': 13,
                'tables': {
                    'forward_filter': [],
                    'input_filter': [],
                    'internals': [],
                    'output_filter': [],
                    'post_routing': [
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
                                    }
                                ]
                            }, {
                                'name': 'forward',
                                'ports': ['foo_2']
                            }],
                            'idx': 2,
                            'in_ports': ['in'],
                            'mapping': {
                                'in_port': 32,
                                'length': 64,
                                'out_port': 0
                            },
                            'match': {
                                'fields': [{
                                    'name': 'out_port',
                                    'value': 'foo.2',
                                    'negated' : False
                                }]
                            },
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
                                    'value': 'foo.1',
                                    'negated' : False
                                }, {
                                    'name': 'out_port',
                                    'value': 'foo.2',
                                    'negated' : False
                                }]
                            },
                            'node': 'foo',
                            'tid': 'post_routing'
                        }
                    ],
                    'pre_routing': [],
                    'routing' : []
                },
                'type': 'packet_filter',
                'wiring': [
                    ("pre_routing_input", "input_filter_in"),
                    ("input_filter_accept", "internals_in"),
                    ("pre_routing_forward", "forward_filter_in"),
                    ("forward_filter_accept", "routing_in"),
                    ("internals_out", "output_filter_in"),
                    ("output_filter_accept", "routing_in"),
                    ("routing_out", "post_routing_in")
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
