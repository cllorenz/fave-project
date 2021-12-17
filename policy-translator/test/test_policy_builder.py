#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2019 Claas Lorenz

# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

""" This module provides unit tests for the PolicyBuilder class.
"""

import unittest

from policy import Policy
from policy_builder import PolicyBuilder

class TestPolicyBuilder(unittest.TestCase):

    """ This class provides unit tests for the PolicyBuilder class.
    """

    def setUp(self):
        self.service_str = '\n'.join([
            "# Service HTTP without TLS",
            "describe service HTTP",
            "\tport = 80",
            "\tprotocol = 'tcp'",
            "end"
        ])

        self.role_str = '\n'.join([
            "# Represents all webservers",
            "def role WebService",
            "\thosts = 'http1.foo.bar','http2.foo.bar'",
            "\tvlan = 23",
            "\toffers HTTP",
            "end"
        ])

        self.policy_str = '\n'.join([
            "define policies (default: deny)",
            "# Only allow communication to the webservices via HTTP",
            "\tInternet <->> WebService.HTTP",
            "end"
        ])

        self.policy = Policy()
        self.expectation = Policy()


    def tearDown(self):
        del self.policy
        del self.expectation


    def test_build_roles_and_services(self):

        """ Tests building roles and services from their respective string
            representation.
        """

        PolicyBuilder.build_roles_and_services(
            "%s\n%s\n" % (self.service_str, self.role_str), self.policy
        )

        self.expectation.add_role("WebService")
        self.expectation.add_service("HTTP")

        self.expectation.services["HTTP"].add_attribute("port", "80")
        self.expectation.services["HTTP"].add_attribute("protocol", "\"tcp\"")

        self.expectation.roles["WebService"].add_attribute(
            "hosts", "\"http1.foo.bar\",\"http2.foo.bar\""
        )
        self.expectation.roles["WebService"].add_attribute("vlan", "23")
        self.expectation.roles["WebService"].add_service("HTTP")

        self.assertEqual(self.policy, self.expectation)


    def test_build_policies(self):

        """ Tests building policies from its string representation.
        """

        self.test_build_roles_and_services()

        PolicyBuilder.build_policies(self.policy_str + '\n', self.policy)

        self.expectation.add_reachability_policy(
            "Internet", "WebService", service_to="HTTP"
        )
        self.expectation.add_reachability_policy(
            "Internet", "WebService", condition={"state": "RELATED,ESTABLISHED"}
        )

        self.assertEqual(self.policy, self.expectation)

    def test_build(self):

        """ Test building roles, services, and policies from their string
            representations.
        """

        self.test_build_policies()

        policy = Policy()
        PolicyBuilder.build(
            "%s\n%s\n%s\n" % (self.role_str, self.service_str, self.policy_str),
            policy
        )

        self.assertEqual(policy, self.expectation)


if __name__ == '__main__':
    unittest.main()
