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

""" This module provides unit tests for switch rules.
"""

import unittest

from rule.rule_model import Rule, Match, Forward, Miss, Rewrite, RuleField
from netplumber.mapping import Mapping


class TestRuleField(unittest.TestCase):
    """ This class tests switch rule fields.
    """

    def setUp(self):
        self.rule_field = RuleField("packet.ipv6.source", "2001:db8::1")


    def tearDown(self):
        del self.rule_field


    def test_to_json(self):
        """ Tests converting a field to json.
        """

        self.assertEqual(
            self.rule_field.to_json(),
            {
                "name" : "packet.ipv6.source",
                "value" : "2001:db8::1",
                "negated" : False
            }
        )


    def test_eq(self):
        """ Tests equality of fields.
        """

        nrf1 = RuleField("packet.ipv6.source", "2001:db8::1")
        nrf2 = RuleField("packet.ipv6.destination", "2001:db8::1")
        nrf3 = RuleField("packet.ipv6.source", "2001:db8::2")

        self.assertEqual(self.rule_field, nrf1)
        self.assertNotEqual(self.rule_field, nrf2)
        self.assertNotEqual(self.rule_field, nrf3)
        self.assertNotEqual(nrf2, nrf3)

        self.rule_field.vectorize()
        nrf1.vectorize()
        nrf2.vectorize()
        nrf3.vectorize()

        self.assertEqual(self.rule_field, nrf1)
        self.assertNotEqual(self.rule_field, nrf2)
        self.assertNotEqual(self.rule_field, nrf3)
        self.assertNotEqual(nrf2, nrf3)


    def test_from_json(self):
        """ Tests creating a field from json.
        """

        self.assertEqual(
            RuleField.from_json({
                "name" : "packet.ipv6.source",
                "value" : "2001:db8::1",
                "negated" : False
            }),
            self.rule_field
        )


    def test_vectorize(self):
        """ Tests field vectorization.
        """

        self.rule_field.vectorize()

        self.assertEqual(
            "\
0010000000000001\
0000110110111000\
0000000000000000\
0000000000000000\
0000000000000000\
0000000000000000\
0000000000000000\
0000000000000001",
            self.rule_field.vector.vector
        )



class TestForward(unittest.TestCase):
    """ This class tests forward actions.
    """

    def setUp(self):
        self.fwd = Forward(ports=[1, 2, 3])


    def tearDown(self):
        del self.fwd


    def test_to_json(self):
        """ Tests conversion to json.
        """

        self.assertEqual(
            self.fwd.to_json(),
            {
                "name" : "forward",
                "ports" : [1, 2, 3]
            }
        )


    def test_from_json(self):
        """ Tests construction from json.
        """

        self.assertEqual(
            Forward.from_json({
                "name" : "forward",
                "ports" : [1, 2, 3]
            }),
            self.fwd
        )


    def test_eq(self):
        """ Tests equality of forwarding actions.
        """

        fwd1 = Forward(ports=[1, 2, 3])
        fwd2 = Forward(ports=[1, 2, 4])

        self.assertEqual(self.fwd, fwd1)
        self.assertNotEqual(self.fwd, fwd2)

        fwd3 = Forward(ports=["foo.1"])
        fwd4 = Forward(ports=["foo.1"])
        fwd5 = Forward(ports=["bar.2"])

        self.assertEqual(fwd3, fwd4)
        self.assertNotEqual(fwd3, fwd5)


class TestRewrite(unittest.TestCase):
    """ This class tests rewrite actions.
    """

    def setUp(self):
        self.rewrite = Rewrite(rewrite=[
            RuleField("packet.ipv6.source", "2001:db8::1")
        ])


    def tearDown(self):
        del self.rewrite


    def test_to_json(self):
        """ Tests conversion to json.
        """

        self.assertEqual(
            self.rewrite.to_json(),
            {
                "name" : "rewrite",
                "rw" : [{"name" : "packet.ipv6.source", "value" : "2001:db8::1", "negated" : False}]
            }
        )


    def test_from_json(self):
        """ Tests construction from json.
        """

        self.assertEqual(
            Rewrite.from_json({
                "name" : "rewrite",
                "rw" : [{"name" : "packet.ipv6.source", "value" : "2001:db8::1", "negated" : False}]
            }),
            self.rewrite
        )



    def test_eq(self):
        """ Tests equality of rewrite actions.
        """

        rw1 = Rewrite(rewrite=[RuleField("packet.ipv6.source", "2001:db8::1")])
        rw2 = Rewrite(rewrite=[RuleField("packet.ipv6.source", "2001:db8::2")])

        self.assertEqual(self.rewrite, rw1)
        self.assertNotEqual(self.rewrite, rw2)



class TestMiss(unittest.TestCase):
    """ This class tests miss actions.
    """

    def setUp(self):
        self.miss = Miss()


    def tearDown(self):
        del self.miss


    def test_to_json(self):
        """ Tests conversion to json.
        """

        self.assertEqual(
            self.miss.to_json(),
            {
                "name" : "miss"
            }
        )


    def test_from_json(self):
        """ Tests construction from json.
        """

        self.assertEqual(
            Miss.from_json({
                "name" : "miss"
            }),
            self.miss
        )


    def test_eq(self):
        """ Tests equality of miss actions.
        """

        self.assertEqual(self.miss, Miss())


class TestMatch(unittest.TestCase):
    """ This class tests matches.
    """

    def setUp(self):
        self.match = Match(fields=[
            RuleField("packet.ipv6.source", "2001:db8::1"),
            RuleField("packet.ipv6.destination", "2001:db8::2")
        ])

    def tearDown(self):
        del self.match


    def test_to_json(self):
        """ Tests conversion to json.
        """

        self.assertEqual(
            self.match.to_json(),
            {
                "fields" : [{
                    "name" : "packet.ipv6.source",
                    "value" : "2001:db8::1",
                    "negated" : False
                }, {
                    "name" : "packet.ipv6.destination",
                    "value" : "2001:db8::2",
                    "negated" : False
                }]
            }
        )


    def test_from_json(self):
        """ Tests construction from json.
        """

        self.assertEqual(
            Match.from_json({
                "fields" : [
                    {"name" : "packet.ipv6.source", "value" : "2001:db8::1", "negated" : False},
                    {"name" : "packet.ipv6.destination", "value" : "2001:db8::2", "negated" : False}
                ]
            }),
            self.match
        )



class TestRule(unittest.TestCase):
    """ This class tests rules.
    """

    def setUp(self):
        match = Match(fields=[
            RuleField("packet.ipv6.source", "2001:db8::1"),
            RuleField("packet.ipv6.destination", "2001:db8::2")
        ])
        actions = [Forward(ports=[2])]
        self.mapping = Mapping()
        self.mapping.extend("interface")
        self.mapping.extend("packet.ipv6.destination")
        self.mapping.extend("packet.ipv6.source")

        self.rule = Rule(
            "foo", 1, 0,
            in_ports=[1],
            match=match,
            actions=actions
        )


    def tearDown(self):
        del self.rule
        del self.mapping


    def test_to_json(self):
        """ Tests conversion to json.
        """

        self.assertEqual(
            self.rule.to_json(),
            {
                "node" : "foo",
                "tid" : 1,
                "idx" : 0,
                "in_ports" : [1],
                "match" : {
                    "fields" : [{
                        "name" : "packet.ipv6.source",
                        "value" : "2001:db8::1",
                        "negated" : False
                    }, {
                        "name" : "packet.ipv6.destination",
                        "value" : "2001:db8::2",
                        "negated" : False
                    }]
                },
                "actions" : [{"name" : "forward", "ports" : [2]}]
            }
        )



    def test_from_json(self):
        """ Tests construction from json.
        """

        self.assertEqual(
            Rule.from_json({
                "node" : "foo",
                "tid" : 1,
                "idx" : 0,
                "in_ports" : [1],
                "match" : {
                    "fields" : [{
                        "name" : "packet.ipv6.source",
                        "value" : "2001:db8::1",
                        "negated" : False
                    }, {
                        "name" : "packet.ipv6.destination",
                        "value" : "2001:db8::2",
                        "negated" : False
                    }]
                },
                "actions" : [{"name" : "forward", "ports" : [2]}]
            }),
            self.rule
        )



    def test_eq(self):
        """ Tests rule equality.
        """

        match1 = Match(fields=[
            RuleField("packet.ipv6.source", "2001:db8::1"),
            RuleField("packet.ipv6.destination", "2001:db8::2")
        ])
        actions1 = [Forward(ports=[2])]

        rule1 = Rule(
            "foo", 1, 0,
            in_ports=[1],
            match=match1,
            actions=actions1
        )

        self.assertEqual(self.rule, rule1)

        rule2 = Rule(
            "bar", 2, 1,
            in_ports=[1],
            match=match1,
            actions=actions1
        )

        self.assertNotEqual(self.rule, rule2)

        rule3 = Rule(
            "foo", 1, 0,
            in_ports=[1, 2],
            match=match1,
            actions=actions1
        )

        self.assertNotEqual(self.rule, rule3)

        match2 = Match(fields=[
            RuleField("packet.ipv6.source", "2001:db8::3")
        ])
        rule4 = Rule(
            "foo", 1, 0,
            in_ports=[1],
            match=match2,
            actions=actions1
        )

        self.assertNotEqual(self.rule, rule4)

        actions2 = [
            Rewrite(rewrite=[
                RuleField("packet.ipv6.source", "2001:db8::3")
            ])
        ]
        rule5 = Rule(
            "foo", 1, 0,
            in_ports=[1],
            match=match1,
            actions=actions2
        )

        self.assertNotEqual(self.rule, rule5)


if __name__ == '__main__':
    unittest.main()
