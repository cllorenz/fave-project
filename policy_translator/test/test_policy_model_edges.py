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

""" The parts of the Policy model no other test reaches: its refusals, the
`IgnorePolicy` a report CSV produces, `to_html` under `default: allow`,
`vlans_to_csv`, and `to_prosa`'s guard for an operator it does not know.

Pinned:

  * every refusal names the right exception: a name already taken by a role
    or service, an unknown role on either side of a rule or ignore entry, an
    unknown service on a role or as a superrole member's service, an invalid
    attribute key or value on a role or a service;
  * comparing a model object with something else is `NotImplemented`, so
    `==` is False -- except a Superrole against a Role, which raises
    AttributeError (expectedFailure, `test_superrole_and_role_...`);
  * `Superrole.add_subrole(group, service)` resolves the group to its members
    and adds the service through each of them;
  * `IgnorePolicy.update_conditions` keeps the least strict conditions, and
    an empty list (unconditional) wins;
  * `to_html` under `default: allow` frames a conditional cell as NICHT(...);
  * `vlans_to_csv` on `examples/ifi-policy.txt`;
  * `to_prosa` names an operator neither of its tables knows.

And a finding, as an expectedFailure: non-strict mode's self-reachability
rules are PROHIBITIONS under `default: allow`
(`TestDefaultAllowSelfReachability`).
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy, Superrole, IgnorePolicy
from policy_builder import PolicyBuilder
from policy_exceptions import (
    NameTakenException, InvalidAttributeException, InvalidValueException,
    RoleUnknownException, ServiceUnknownException,
)


_PT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_INVENTORY = """def service SSH
    protocol = 'tcp'
    port = 22
end

def role Alpha
    ipv6 = '2001:db8::1/128'
    offers SSH
end

def role Beta
    ipv6 = '2001:db8::2/128'
    offers SSH
end

def role Group
    includes Alpha
    includes Beta
end

"""


def _build(text, **kwargs):
    policy = Policy(**kwargs)
    PolicyBuilder.build(text, policy)
    return policy


class TestRefusals(unittest.TestCase):

    def setUp(self):
        self.policy = _build(_INVENTORY)

    def test_names_are_unique_across_roles_and_services(self):
        with self.assertRaises(NameTakenException):
            self.policy.add_superrole('Alpha')
        with self.assertRaises(NameTakenException):
            self.policy.add_service('SSH')
        with self.assertRaises(NameTakenException):
            self.policy.add_service('Alpha')

    def test_unknown_roles_in_rules(self):
        with self.assertRaises(RoleUnknownException):
            self.policy.add_reachability_policy('Nobody', 'Alpha')
        with self.assertRaises(RoleUnknownException):
            self.policy.add_reachability_policy('Alpha', 'Nobody')
        with self.assertRaises(RoleUnknownException):
            self.policy.add_ignore_policy('Nobody', 'Alpha')
        with self.assertRaises(RoleUnknownException) as cm:
            self.policy.add_ignore_policy('Alpha', 'Nobody')
        self.assertEqual(cm.exception.message, "Role Nobody is unknown.")

    def test_unknown_services(self):
        with self.assertRaises(ServiceUnknownException) as cm:
            self.policy.roles['Alpha'].add_service('HTTP')
        self.assertEqual(cm.exception.message, "Service HTTP is unknown.")
        group = self.policy.roles['Group']
        with self.assertRaises(ServiceUnknownException) as cm:
            group.add_subservice('Alpha', 'HTTP')
        self.assertEqual(cm.exception.message, "Service Alpha.HTTP is unknown.")

    def test_unknown_superrole_member(self):
        with self.assertRaises(RoleUnknownException):
            self.policy.roles['Group'].add_subrole('Nobody')

    def test_invalid_attributes(self):
        alpha = self.policy.roles['Alpha']
        with self.assertRaises(InvalidAttributeException) as cm:
            alpha.add_attribute('colour', "'red'")
        self.assertEqual(cm.exception.message, "Attribute colour is invalid.")
        ssh = self.policy.services['SSH']
        with self.assertRaises(InvalidAttributeException):
            ssh.add_attribute('colour', "'red'")
        with self.assertRaises(InvalidValueException) as cm:
            ssh.add_attribute('port', "twenty-two")
        self.assertEqual(cm.exception.message,
                         "Attribute value port = twenty-two is invalid.")
        self.assertEqual(ssh.attributes, {'protocol': 'tcp', 'port': 22})

    def test_comparison_with_other_types(self):
        self.assertFalse(self.policy == 'policy')
        self.assertFalse(self.policy.roles['Alpha'] == 'Alpha')
        self.assertFalse(self.policy.roles['Group'] == 'Group')

    # DEFECT (policy.py:1129): `Superrole.__eq__` declines a plain Role, so
    # Python tries the reflected `Role.__eq__`, which reads `.attributes` --
    # an attribute `Superrole.__init__` never sets. Comparing a superrole with
    # a role raises AttributeError instead of answering False.
    @unittest.expectedFailure
    def test_superrole_and_role_compare_unequal(self):
        self.assertNotEqual(self.policy.roles['Group'],
                            self.policy.roles['Alpha'])


class TestSuperroleMembersWithService(unittest.TestCase):

    def test_group_member_with_a_service_resolves_to_its_members(self):
        policy = _build(_INVENTORY)
        policy.add_superrole('Outer')
        outer = policy.roles['Outer']
        assert isinstance(outer, Superrole)
        outer.add_subrole('Group', service='SSH')
        self.assertEqual(sorted(outer.subroles), ['Alpha', 'Beta'])
        self.assertEqual(
            {member: sorted(services)
             for member, services in outer.subservices.items()},
            {'Alpha': ['SSH'], 'Beta': ['SSH']})

    def test_service_to_json(self):
        policy = _build(_INVENTORY)
        self.assertEqual(policy.services['SSH'].to_json(), {
            'name': 'SSH', 'attributes': {'protocol': 'tcp', 'port': 22}})


class TestIgnorePolicy(unittest.TestCase):

    def test_equality(self):
        policy = Policy()
        one = IgnorePolicy('A', 'B', policy, [{'state': 'NEW'}])
        self.assertEqual(one, IgnorePolicy('A', 'B', policy, [{'state': 'NEW'}]))
        self.assertNotEqual(one, IgnorePolicy('A', 'C', policy, [{'state': 'NEW'}]))

    def test_conditions_are_deep_copied(self):
        conditions = [{'state': 'NEW'}]
        ignore = IgnorePolicy('A', 'B', Policy(), conditions)
        conditions[0]['state'] = 'INVALID'
        self.assertEqual(ignore.conditions, [{'state': 'NEW'}])

    def test_update_conditions(self):
        policy = Policy()
        ignore = IgnorePolicy('A', 'B', policy,
                              [{'state': 'NEW', 'port': 22}])
        # A stricter condition (a superset) is discarded.
        ignore.update_conditions([{'state': 'NEW', 'port': 22, 'proto': 'tcp'}])
        self.assertEqual(ignore.conditions, [{'state': 'NEW', 'port': 22}])
        # A less strict one (a strict subset) replaces it.
        ignore.update_conditions([{'state': 'NEW'}])
        self.assertEqual(ignore.conditions, [{'state': 'NEW'}])
        # An unrelated one is an additional alternative.
        ignore.update_conditions([{'port': 80}])
        self.assertEqual(ignore.conditions, [{'state': 'NEW'}, {'port': 80}])
        # Unconditional wins, and stays unconditional.
        ignore.update_conditions([])
        self.assertEqual(ignore.conditions, [])
        ignore.update_conditions([{'port': 443}])
        self.assertEqual(ignore.conditions, [])


class TestRenderers(unittest.TestCase):

    def test_html_under_default_allow_negates_conditions(self):
        policy = _build(_INVENTORY + (
            "def policies(default: allow)\n"
            "    Alpha -/->> Beta\n"
            "end\n"))
        html = policy.to_html()
        self.assertIn("<span class='tooltiptext'>NICHT<br/>(</br>"
                      "state = NEW,INVALID<br/>)</span>", html)

    def test_vlans_to_csv(self):
        with open(os.path.join(_PT, 'examples', 'ifi-policy.txt')) as f:
            policy = _build(f.read())
        self.assertEqual(policy.vlans_to_csv(), (
            ",1,2,3,4,5,6\n"
            "1,X,X,X,X,X,X\n"
            "2,X,X,,,X,X\n"
            "3,X,,X,,X,X\n"
            "4,X,,,X,X,X\n"
            "5,X,X,X,X,X,X\n"
            "6,X,X,X,X,X,X\n"))

    def test_prosa_names_an_unknown_operator(self):
        policy = _build(_INVENTORY + (
            "def policies(default: deny)\n"
            "    Alpha ---> Beta\n"
            "end\n"))
        policy.raw_policies[('Alpha', 'Beta', None, '~~>')] = None
        lines = policy.to_prosa().splitlines()
        self.assertEqual(lines[-2:], [
            "Alpha ~~> Beta",
            "\tUNKNOWN OPERATOR `~~>` -- neither `Policy.prosa_permits` nor "
            "`Policy.prosa_forbids` knows it.",
        ])


class TestDefaultAllowSelfReachability(unittest.TestCase):
    """ FINDING. Non-strict mode adds `role ---> role` for every atomic role
    (`PolicyBuilder.build_policies`, policy_builder.py:427), to let a role
    reach itself without an explicit rule. Under `default: allow` an entry in
    `Policy.policies` is a PROHIBITION, so the same loop forbids every role
    to reach itself: `to_iptables` emits `... "Alpha to Alpha" -j DROP`.
    Remove the decorator once the loop is limited to `default: deny`.
    """

    @unittest.expectedFailure
    def test_self_traffic_is_not_dropped(self):
        policy = _build(_INVENTORY + (
            "def policies(default: allow)\n"
            "    Alpha --/-> Beta\n"
            "end\n"))
        self.assertNotIn('"Alpha to Alpha" -j DROP', policy.to_iptables())

    def test_explicit_prohibition_is_dropped(self):
        policy = _build(_INVENTORY + (
            "def policies(default: allow)\n"
            "    Alpha --/-> Beta\n"
            "end\n"))
        self.assertIn('"Alpha to Beta" -j DROP', policy.to_iptables())


if __name__ == '__main__':
    unittest.main()
