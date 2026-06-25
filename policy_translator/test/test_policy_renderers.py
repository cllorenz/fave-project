#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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

""" Tests the Policy model's renderers, atomic-role resolution, and the
ReachabilityPolicy condition-merging logic -- the pure parts of policy.py that
had no direct coverage.
"""

import json
import unittest

from policy import Policy, ReachabilityPolicy


def _policy_with_roles():
    """ A small strict policy: roles A (vlan 10, ipv4) and B (vlan 20). """
    policy = Policy(use_internet=False, strict=True)
    policy.add_role('A')
    policy.add_role('B')
    policy.roles['A'].add_attribute('vlan', '10')
    policy.roles['A'].add_attribute('ipv4', '"10.0.0.1"')
    policy.roles['B'].add_attribute('vlan', '20')
    return policy


class TestAtomicRoles(unittest.TestCase):
    """ Tests resolution of atomic roles, including superrole expansion. """

    def test_plain_roles_are_atomic(self):
        policy = _policy_with_roles()
        self.assertEqual(policy.get_atomic_roles(), {'A', 'B'})

    def test_superrole_expands_to_its_atomic_members(self):
        policy = Policy(use_internet=False, strict=True)
        policy.add_role('web1')
        policy.add_role('web2')
        policy.add_superrole('webservers')
        policy.roles['webservers'].add_subrole('web1')
        policy.roles['webservers'].add_subrole('web2')

        # The superrole itself is not atomic ...
        self.assertEqual(policy.get_atomic_roles(), {'web1', 'web2'})
        # ... but resolving it yields its atomic members.
        self.assertEqual(
            policy.get_atomic_roles_rec(['webservers']), {'web1', 'web2'}
        )


class TestRenderers(unittest.TestCase):
    """ Tests the role/attribute output renderers. """

    def test_to_mapping_emits_role_attributes(self):
        """ to_mapping is a JSON role->attributes map (Role only). Note attribute
        values are ast.literal_eval'd: vlan '10' -> int, ipv4 '"x"' -> str. """
        mapping = json.loads(_policy_with_roles().to_mapping())
        self.assertEqual(mapping, {
            'A': {'vlan': 10, 'ipv4': '10.0.0.1'},
            'B': {'vlan': 20},
        })

    def test_roles_to_json_dumps_atomic_roles(self):
        result = _policy_with_roles().roles_to_json()
        by_name = {r['name']: r for r in result}
        self.assertEqual(set(by_name), {'A', 'B'})
        self.assertEqual(by_name['A']['attributes'], {'vlan': 10, 'ipv4': '10.0.0.1'})
        self.assertEqual(by_name['B']['attributes'], {'vlan': 20})

    def test_vlans_to_csv_matrix(self):
        """ vlans_to_csv is a vlan-by-vlan reachability matrix (header + rows). """
        csv = _policy_with_roles().vlans_to_csv()
        rows = csv.strip().split('\n')
        self.assertEqual(rows[0], ',10,20')          # header: the two vlans
        self.assertEqual(len(rows), 3)               # header + one row per vlan

    def test_roles_to_csv_matrix(self):
        """ roles_to_csv marks reachable role pairs with 'X'. """
        policy = Policy(use_internet=False, strict=True)
        policy.add_role('A')
        policy.add_role('B')
        policy.add_reachability_policy('A', 'B')
        csv = policy.roles_to_csv()
        self.assertEqual(csv, ',A,B\nA,,X\nB,,\n')   # A reaches B; nothing else

    def _html_policy(self, default):
        policy = Policy(use_internet=False, strict=True)
        policy.set_default_policy(default)
        policy.add_role('A')
        policy.add_role('B')
        policy.add_service('HTTP')
        policy.services['HTTP'].add_attribute('port', '80')
        policy.services['HTTP'].add_attribute('protocol', "'tcp'")
        policy.add_reachability_policy('A', 'B')
        return policy

    def test_to_html_is_a_well_formed_doc_with_the_role_matrix(self):
        html = self._html_policy('deny').to_html()
        # A complete HTML document ...
        self.assertTrue(html.lstrip().startswith('<!DOCTYPE html>'))
        self.assertIn('<html>', html)
        self.assertIn('</html>', html)
        # ... rendering the reachability matrix with both roles.
        self.assertIn('<table>', html)
        self.assertIn('</table>', html)
        self.assertIn('A', html)
        self.assertIn('B', html)

    def test_to_html_renders_under_allow_default(self):
        """ The allow default flips the matrix semantics (XOR path); it must
        still render a complete document. """
        html = self._html_policy('allow').to_html()
        self.assertTrue(html.lstrip().startswith('<!DOCTYPE html>'))
        self.assertIn('</html>', html)


class TestUpdateConditions(unittest.TestCase):
    """ Tests ReachabilityPolicy.update_conditions merge semantics.

    Conditions are OR-ed dicts; a more-specific (superset) condition is
    redundant against a broader existing one, a broader (subset) condition
    replaces the narrower existing one, and an empty list means "unconditional"
    and overpowers everything.
    """

    def _merge(self, initial, new):
        rpol = ReachabilityPolicy('A', 'B', None, initial)
        rpol.update_conditions(new)
        return rpol.conditions

    def test_more_specific_new_condition_is_discarded(self):
        self.assertEqual(
            self._merge([{'port': 80}], [{'port': 80, 'protocol': 'tcp'}]),
            [{'port': 80}]
        )

    def test_broader_new_condition_replaces_existing(self):
        self.assertEqual(
            self._merge([{'port': 80, 'protocol': 'tcp'}], [{'port': 80}]),
            [{'port': 80}]
        )

    def test_disjoint_condition_is_or_appended(self):
        self.assertEqual(
            self._merge([{'port': 80}], [{'state': 'NEW'}]),
            [{'port': 80}, {'state': 'NEW'}]
        )

    def test_empty_existing_stays_unconditional(self):
        self.assertEqual(self._merge([], [{'port': 80}]), [])

    def test_empty_new_overpowers_to_unconditional(self):
        self.assertEqual(self._merge([{'port': 80}], []), [])


class TestPolicyExists(unittest.TestCase):
    """ Tests the policy_exists lookup. """

    def test_policy_exists(self):
        policy = Policy(use_internet=False, strict=True)
        policy.add_role('A')
        policy.add_role('B')
        policy.add_reachability_policy('A', 'B')
        self.assertTrue(policy.policy_exists('A', 'B'))
        self.assertFalse(policy.policy_exists('B', 'A'))


if __name__ == '__main__':
    unittest.main()
