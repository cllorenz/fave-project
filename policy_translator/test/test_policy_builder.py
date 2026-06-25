#!/usr/bin/env python3

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
from policy_exceptions import (
    NameTakenException, InvalidValueException, InvalidSyntaxException,
    RoleUnknownException,
)

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

        # 'Internet <->> WebService.HTTP' under default-deny expands to (see
        # PolicyBuilder.build_policies): a forward policy carrying the HTTP
        # service, a *reverse* RELATED,ESTABLISHED policy for the return path,
        # and -- in non-strict mode -- an implicit self-reachability policy per
        # atomic role. (The previous expectation put the state condition on the
        # forward direction and omitted self-reachability; it only passed
        # because Policy.__eq__ did not compare the policies dict.)
        self.expectation.add_reachability_policy(
            "Internet", "WebService", service_to="HTTP"
        )
        self.expectation.add_reachability_policy(
            "WebService", "Internet", condition={"state": "RELATED,ESTABLISHED"}
        )
        self.expectation.add_reachability_policy("WebService", "WebService")
        self.expectation.add_reachability_policy("Internet", "Internet")

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


class TestPolicyOperators(unittest.TestCase):
    """ Tests the reachability semantics of each FPL operator.

    Uses strict mode so the implicit self-reachability policies are suppressed,
    leaving only the operator's own effect on the policies dict. Conditions are
    asserted directly (not via Policy equality).
    """

    def _build(self, default, operator_line):
        policy = Policy(strict=True)
        policy.add_role('A')
        policy.add_role('B')
        PolicyBuilder.build_policies(
            'define policies (default: %s)\n\t%s\nend\n' % (default, operator_line),
            policy
        )
        return {key: value.conditions for key, value in policy.policies.items()}

    # --- default-deny operators ---------------------------------------------

    def test_stateful_bidirectional_deny(self):
        """ '<->>': forward (unconditional) + reverse RELATED,ESTABLISHED. """
        self.assertEqual(self._build('deny', 'A <->> B'), {
            ('A', 'B'): [],
            ('B', 'A'): [{'state': 'RELATED,ESTABLISHED'}],
        })

    def test_unidirectional_deny(self):
        """ '--->': a single forward policy. """
        self.assertEqual(self._build('deny', 'A ---> B'), {('A', 'B'): []})

    def test_bidirectional_deny(self):
        """ '<-->': forward and reverse, both unconditional. """
        self.assertEqual(self._build('deny', 'A <--> B'), {
            ('A', 'B'): [],
            ('B', 'A'): [],
        })

    def test_deny_only_operators_ignored_under_allow(self):
        """ A deny-default operator is silently ignored under default allow. """
        self.assertEqual(self._build('allow', 'A ---> B'), {})

    # --- default-allow operators ---------------------------------------------

    def test_unidirectional_forbid(self):
        """ '--/->': a single forbidden (forward) policy. """
        self.assertEqual(self._build('allow', 'A --/-> B'), {('A', 'B'): []})

    def test_bidirectional_forbid(self):
        """ '<-/->': forbidden forward and reverse. """
        self.assertEqual(self._build('allow', 'A <-/-> B'), {
            ('A', 'B'): [],
            ('B', 'A'): [],
        })

    def test_stateful_forbid(self):
        """ '-/->>': conditionally forbidden NEW,INVALID. """
        self.assertEqual(self._build('allow', 'A -/->> B'), {
            ('A', 'B'): [{'state': 'NEW,INVALID'}],
        })

    def test_allow_only_operator_ignored_under_deny(self):
        """ An allow-default operator is silently ignored under default deny. """
        self.assertEqual(self._build('deny', 'A --/-> B'), {})

    def test_self_reachability_added_in_non_strict_mode(self):
        """ Non-strict mode adds an implicit role->role policy per atomic role. """
        policy = Policy(strict=False, use_internet=False)
        policy.add_role('A')
        policy.add_role('B')
        PolicyBuilder.build_policies(
            'define policies (default: deny)\n\tA ---> B\nend\n', policy
        )
        self.assertIn(('A', 'A'), policy.policies)
        self.assertIn(('B', 'B'), policy.policies)


class TestPolicyBuilderErrors(unittest.TestCase):
    """ Tests the FPL error/exception paths (previously untested). """

    def test_duplicate_role_raises(self):
        policy = Policy()
        policy.add_role('A')
        with self.assertRaises(NameTakenException):
            policy.add_role('A')

    def test_invalid_attribute_value_raises(self):
        policy = Policy()
        policy.add_role('A')
        with self.assertRaises(InvalidValueException):
            policy.roles['A'].add_attribute('vlan', 'not-a-number')

    def test_malformed_roles_block_raises(self):
        policy = Policy()
        with self.assertRaises(InvalidSyntaxException):
            PolicyBuilder.build_roles_and_services('this is not valid fpl\n', policy)

    def test_policy_referencing_unknown_role_raises(self):
        policy = Policy(strict=True)
        policy.add_role('A')
        with self.assertRaises(RoleUnknownException):
            PolicyBuilder.build_policies(
                'define policies (default: deny)\n\tA ---> Nonexistent\nend\n',
                policy
            )


if __name__ == '__main__':
    unittest.main()
