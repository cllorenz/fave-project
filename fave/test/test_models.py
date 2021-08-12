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
from topology.router import RouterModel
from openflow.switch import SwitchModel, Forward, Rewrite, SwitchRule
from openflow.switch import Match, SwitchRuleField
from util.model_util import TABLE_MAX
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
                'node': 'foo',
                'ports': {
                    'foo.acl_in_in': 'foo.acl_in',
                    'foo.acl_in_out': 'foo.acl_in',
                    'foo.acl_out_in': 'foo.acl_out',
                    'foo.acl_out_out': 'foo.acl_out',
                    'foo.1': '',
                    'foo.2': '',
                    'foo.1_ingress' : 'foo.pre_routing',
                    'foo.2_ingress' : 'foo.pre_routing',
                    'foo.1_egress' : 'foo.post_routing',
                    'foo.2_egress' : 'foo.post_routing',
                    'foo.post_routing_in': 'foo.post_routing',
                    'foo.pre_routing_out': 'foo.pre_routing',
                    'foo.routing_in': 'foo.routing',
                    'foo.routing_out': 'foo.routing'
                },
                'tables': {
                    'foo.acl_in': [{
                        'actions': [],
                        'idx': 1,
                        'in_ports': ['foo.acl_in_in'],
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
                        'tid': 'foo.acl_in'
                    }, {
                        'actions': [],
                        'idx': 2,
                        'in_ports': ['foo.acl_in_in'],
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
                        'tid': 'foo.acl_in'
                    }],
                    'foo.acl_out': [],
                    'foo.post_routing': [{
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
                        'match': {'fields': [{
                            'name': 'out_port',
                            'value': 'foo.1_egress',
                            'negated' : False
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
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
                        'match': {'fields': [{
                            'name': 'out_port',
                            'value': 'foo.2_egress',
                            'negated' : False
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
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
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
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
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
                    }],
                    'foo.pre_routing': [{
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'foo.1_ingress',
                                'negated' : False
                            }]}, {
                                'name': 'forward',
                                'ports': ['foo.pre_routing_out']
                            }
                        ],
                        'idx': 0,
                        'in_ports': ['foo.1_ingress'],
                        'match': None,
                        'node': 'foo',
                        'tid': 'foo.pre_routing'
                    }, {
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'foo.2_ingress',
                                'negated' : False
                            }]}, {
                                'name': 'forward',
                                'ports': ['foo.pre_routing_out']
                            }
                        ],
                        'idx': 1,
                        'in_ports': ['foo.2_ingress'],
                        'match': None,
                        'node': 'foo',
                        'tid': 'foo.pre_routing'
                    }],
                    'foo.routing': []
                },
                'type': 'router',
                'wiring': [
                    ('foo.pre_routing_out', 'foo.acl_in_in'),
                    ('foo.acl_in_out', 'foo.routing_in'),
                    ('foo.routing_out', 'foo.acl_out_in'),
                    ('foo.acl_out_out', 'foo.post_routing_in')
                ]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a router model from JSON.
        """

        router = RouterModel.from_json({
                'node': 'foo',
                'ports': {
                    'foo.acl_in_in': 'foo.acl_in',
                    'foo.acl_in_out': 'foo.acl_in',
                    'foo.acl_out_in': 'foo.acl_out',
                    'foo.acl_out_out': 'foo.acl_out',
                    'foo.1': '',
                    'foo.2': '',
                    'foo.1_ingress' : 'foo.pre_routing',
                    'foo.2_ingress' : 'foo.pre_routing',
                    'foo.1_egress' : 'foo.post_routing',
                    'foo.2_egress' : 'foo.post_routing',
                    'foo.post_routing_in': 'foo.post_routing',
                    'foo.pre_routing_out': 'foo.pre_routing',
                    'foo.routing_in': 'foo.routing',
                    'foo.routing_out': 'foo.routing'
                },
                'tables': {
                    'foo.acl_in': [{
                        'actions': [],
                        'idx': 1,
                        'in_ports': ['foo.acl_in_in'],
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
                        'tid': 'foo.acl_in'
                    }, {
                        'actions': [],
                        'idx': 2,
                        'in_ports': ['foo.acl_in_in'],
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
                        'tid': 'foo.acl_in'
                    }],
                    'foo.acl_out': [],
                    'foo.post_routing': [{
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
                        'match': {'fields': [{
                            'name': 'out_port',
                            'value': 'foo.1_egress',
                            'negated' : False
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
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
                        'match': {'fields': [{
                            'name': 'out_port',
                            'value': 'foo.2_egress',
                            'negated' : False
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
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
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
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
                        }]},
                        'node': 'foo',
                        'tid': 'foo.post_routing'
                    }],
                    'foo.pre_routing': [{
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'foo.1_ingress',
                                'negated' : False
                            }]}, {
                                'name': 'forward',
                                'ports': ['foo.pre_routing_out']
                            }
                        ],
                        'idx': 0,
                        'in_ports': ['foo.1_ingress'],
                        'match': None,
                        'node': 'foo',
                        'tid': 'foo.pre_routing'
                    }, {
                        'actions': [{
                            'name': 'rewrite',
                            'rw': [{
                                'name': 'in_port',
                                'value': 'foo.2_ingress',
                                'negated' : False
                            }]}, {
                                'name': 'forward',
                                'ports': ['foo.pre_routing_out']
                            }
                        ],
                        'idx': 1,
                        'in_ports': ['foo.2_ingress'],
                        'match': None,
                        'node': 'foo',
                        'tid': 'foo.pre_routing'
                    }],
                    'foo.routing': []
                },
                'type': 'router',
                'wiring': [
                    ('foo.pre_routing_out', 'foo.acl_in_in'),
                    ('foo.acl_in_out', 'foo.routing_in'),
                    ('foo.routing_out', 'foo.acl_out_in'),
                    ('foo.acl_out_out', 'foo.post_routing_in')
                ]
            })

        self.assertEqual(
            router,
            self.model
        )


    def test_complex(self):
        """ Tests the a more complex model.
        """

        ports = ['1', '2']
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
                'node': 'foo',
                'ports': {},
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

        model1.add_rule(SwitchRule("foo", 1, TABLE_MAX, actions=[]))

        match1 = Match(fields=[SwitchRuleField(
            OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:1::0/48"
        )])
        actions1 = [Forward(['foo.1'])]
        model1.add_rule(
            SwitchRule(
                "foo", 1, 0,
                in_ports=['foo.1', 'foo.2'],
                match=match1,
                actions=actions1
            )
        )

        match2 = Match(fields=[SwitchRuleField(
            OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:2::0/48"
        )])
        actions2 = [
            Rewrite([SwitchRuleField(
                OXM_FIELD_TO_MATCH_FIELD["ipv6_dst"], "2001:db8:3::0/48"
            )]),
            Forward(['foo.4'])
        ]
        model1.add_rule(
            SwitchRule(
                "foo", 1, 1,
                in_ports=['foo.1', 'foo.2', 'foo.3'],
                match=match2,
                actions=actions2
            )
        )

        model2 = SwitchModel.from_json(model1.to_json())

        self.assertEqual(model1, model2)



if __name__ == '__main__':
    unittest.main()
