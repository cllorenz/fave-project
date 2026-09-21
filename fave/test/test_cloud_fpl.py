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

""" wl_cloud's FPL inventory, against the model it claims to describe.

THE INVENTORY IS THE ONE HAND-WRITTEN INPUT of this workload (§1.9): the dataset
ships no roles, and a policy is an intent that cannot be derived from data. That
makes it the one place a typo cannot be caught by regenerating anything -- a
role naming a node that does not exist, or carrying an address that is not the
one its generator injects, would produce checks FaVe answers confidently about
the wrong host.

So the two halves are pinned against each other here: the endpoint derivation
(which IS derived, from `node_name`'s own arithmetic) and the committed
inventory file.
"""

import json
import os
import tempfile
import unittest

from bench.wl_cloud.cloud_endpoints import (
    INTERNET, InventoryError, derive_endpoints, role_members)
from bench.wl_cloud.cloud_tf import classify_nodes, parse_tf

_RAW = 'bench/wl_cloud/cloud-tf/network.tf'
_INVENTORY = 'bench/wl_cloud/roles_and_services.txt'
_POLICY = 'bench/wl_cloud/reach.txt'


def _roles_json(path):
    """ `policy_translator --roles` for the committed inventory. """
    import subprocess
    import sys
    handle, out = tempfile.mkstemp(suffix='.json')
    os.close(handle)
    subprocess.run(
        [sys.executable, '../policy_translator/policy_translator.py',
         '--strict', '--roles', out, '--csv', '--out', os.devnull,
         _INVENTORY, _POLICY],
        check=True)
    return out


@unittest.skipUnless(os.path.isfile(_RAW), 'raw scenario not present')
class TestTheEndpointDerivation(unittest.TestCase):
    """ What an FPL role is allowed to name. """

    @classmethod
    def setUpClass(cls):
        cls.model = classify_nodes(parse_tf(open(_RAW, 'r')))
        cls.endpoints = derive_endpoints(cls.model)

    def test_every_host_contributes_one_endpoint_with_both_sides(self):
        """ A host is two nodes in the dataset and ONE name in a policy: the
        `_tx` it injects at and the `_rx` it is observed at. """
        endpoint = self.endpoints['dc0_leaf1_host1']
        self.assertEqual(endpoint.tx, 1000068)
        self.assertEqual(endpoint.rx, 1000067)

    def test_an_endpoint_carries_the_address_its_generator_injects(self):
        """ Not a declared address -- the one read off the transmit node's own
        rule, which is exactly what `_inject` prepends to the generator. """
        self.assertEqual(self.endpoints['dc1_leaf6_host0'].ipv4, '10.0.7.0/30')

    def test_the_internet_is_paired_by_hand_because_it_is_not_a_host(self):
        """ The gateway is a DEVICE -- it holds the inbound NAT rules -- so the
        `_rx`/`_tx` rule that pairs hosts cannot pair it, and a generator has to
        attach to the gateway directly for anything to enter from outside. """
        internet = self.endpoints[INTERNET]
        self.assertIn(internet.tx, set(self.model.devices))
        self.assertIn(internet.rx, set(self.model.sinks))
        self.assertIsNone(internet.ipv4)

    def test_a_half_pair_contributes_no_endpoint(self):
        """ A name resolving to only one side would give a role a generator
        with no probe or the reverse, and every check naming it would then fail
        for a reason that has nothing to do with the network. """
        for name, endpoint in self.endpoints.items():
            self.assertIsNotNone(endpoint.tx, name)
            self.assertIsNotNone(endpoint.rx, name)


@unittest.skipUnless(os.path.isfile(_RAW), 'raw scenario not present')
class TestTheCommittedInventory(unittest.TestCase):
    """ The hand-written file against the derived model. """

    @classmethod
    def setUpClass(cls):
        cls.endpoints = derive_endpoints(classify_nodes(parse_tf(open(_RAW, 'r'))))
        cls.roles_path = _roles_json(_INVENTORY)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.roles_path)

    def test_every_committed_role_names_a_real_endpoint_with_its_address(self):
        """ The whole point of this file. `role_members` raises on either kind
        of mismatch, so reaching the assertions means both held. """
        members = role_members(self.roles_path, self.endpoints)

        self.assertIn('Internet', members)
        self.assertEqual(members['Internet'].name, INTERNET)
        self.assertEqual(
            members['dc4_leaf3_host22'].ipv4, '10.0.17.216/30')
        # One role per endpoint the six queries name, plus Internet.
        self.assertEqual(len(members), 8)

    def test_a_role_naming_no_endpoint_is_refused(self):
        """ Not skipped: the checks it generates would address a generator that
        was never built, and every one of them would fail for that reason
        rather than for anything about the network. """
        with self.assertRaises(InventoryError) as ctx:
            role_members(
                self._roles([{'name': 'dc9_leaf9_host9', 'attributes': {}}]),
                self.endpoints)
        self.assertIn('dc9_leaf9_host9', str(ctx.exception))

    def test_a_role_declaring_the_wrong_address_is_refused(self):
        """ The failure this catches is silent by construction: the policy
        names one host and the generator injects another's traffic, so every
        answer is confident and about the wrong thing. """
        with self.assertRaises(InventoryError) as ctx:
            role_members(
                self._roles([{'name': 'dc1_leaf6_host0',
                              'attributes': {'ipv4': '10.0.7.8/30'}}]),
                self.endpoints)
        self.assertIn('10.0.7.8/30', str(ctx.exception))

    def test_a_role_declaring_no_address_is_accepted(self):
        """ `Internet` has none -- the gateway is a device with no `/30` -- so
        an absent declaration is not a mismatch. """
        members = role_members(
            self._roles([{'name': 'dc1_leaf6_host0', 'attributes': {}}]),
            self.endpoints)
        self.assertEqual(members['dc1_leaf6_host0'].ipv4, '10.0.7.0/30')

    def _roles(self, roles):
        handle, path = tempfile.mkstemp(suffix='.json')
        os.close(handle)
        self.addCleanup(os.unlink, path)
        with open(path, 'w') as out:
            out.write(json.dumps(roles))
        return path


if __name__ == '__main__':
    unittest.main()
