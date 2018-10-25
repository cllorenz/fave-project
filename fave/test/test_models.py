#!/usr/bin/env python2

""" This module provides tests for router models.
"""

import unittest

from netplumber.model import Model
from topology.router import Router


class TestRouterModel(unittest.TestCase):
    """ This class provides tests for the router model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = Router("foo")


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
                'mapping': {'interface': 0, 'length': 16},
                'node': 'foo',
                'ports': {
                    'acl_in_out': 1,
                    'acl_out_in': 4,
                    'acl_out_out': 5,
                    'in_1': 9,
                    'out_2': 11,
                    'post_routing_in': 6,
                    'routing_in': 2,
                    'routing_out': 3
                },
                'tables': {
                    'acl_in': [],
                    'acl_out': [],
                    'post_routing': [{
                        'actions': [
                            {'name': 'rewrite', 'rw': [
                                {'name': 'interface', 'value': 'xxxxxxxxxxxxxxxx'}
                            ]},
                            {'name': 'forward', 'ports': ['out_2']}
                        ],
                        'idx': 0,
                        'in_ports': [],
                        'mapping': {'interface': 0, 'length': 16},
                        'match': {
                            'fields': [{
                                'name': 'interface',
                                'value': '0000000000001011'
                            }]
                        },
                        'node': 'foo',
                        'tid': 'post_routing'
                    }],
                    'routing': []
                },
                'type': 'router',
                'wiring': [
                    ('acl_in_out', 'routing_in'),
                    ('routing_out', 'acl_out_in'),
                    ('acl_out_out', 'post_routing_in')
                ]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a router model from JSON.
        """

        self.assertEqual(
            Router.from_json({
                'mapping': {'interface': 0, 'length': 16},
                'node': 'foo',
                'ports': {
                    'acl_in_out': 1,
                    'acl_out_in': 4,
                    'acl_out_out': 5,
                    'in_1': 9,
                    'out_2': 11,
                    'post_routing_in': 6,
                    'routing_in': 2,
                    'routing_out': 3
                },
                'tables': {
                    'acl_in': [],
                    'acl_out': [],
                    'post_routing': [{
                        'actions': [
                            {'name': 'rewrite', 'rw': [
                                {'name': 'interface', 'value': 'xxxxxxxxxxxxxxxx'}
                            ]},
                            {'name': 'forward', 'ports': ['out_2']}
                        ],
                        'idx': 0,
                        'in_ports': [],
                        'mapping': {'interface': 0, 'length': 16},
                        'match': {
                            'fields': [{
                                'name': 'interface',
                                'value': '0000000000001011'
                            }]
                        },
                        'node': 'foo',
                        'tid': 'post_routing'
                    }],
                    'routing': []
                },
                'type': 'router',
                'wiring': [
                    ('acl_in_out', 'routing_in'),
                    ('routing_out', 'acl_out_in'),
                    ('acl_out_out', 'post_routing_in')
                ]
            }),
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

        router1 = Router(
            "foo",
            ports=ports,
            acls=acls,
            routes=routes,
            vlan_to_ports=vlan_to_ports,
            vlan_to_acls=vlan_to_acls
        )

        router2 = Router.from_json(router1.to_json())

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


if __name__ == '__main__':
    unittest.main()
