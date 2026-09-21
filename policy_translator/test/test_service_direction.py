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

""" A service's direction: `provider` says which side offers it.

`A <--> B.S` must yield reachability A->B constrained by S's attributes in
FORWARD direction (`protocol=tcp, port=80`) and reachability B->A constrained by
them in REVERSE direction (`protocol=tcp, sport=80`). The marker for "which side
offers the service" is the `provider` condition key, and `Policy.to_iptables`
has always read it exactly that way:

    serviceport = " --sport " if provider == from_ else " --dport "

WHAT WAS WRONG. `add_reachability_policy` seeded `conditions` with the provider
dict and then APPENDED the service attributes as a further element -- and
elements of that list are OR operands. So one condition became two:
`{"provider": "B"}` OR `{"protocol": "tcp", "port": 80}`. Three consequences,
all of them silent:

  * the CSV grew a `provider:B` operand of its own, which
    `reach_csv_to_checks` emitted as `f=provider:B` and `compliance_checker`
    then died on with `KeyError: 'provider'`;
  * `to_iptables` saw a provider without a protocol and a protocol without a
    provider, so its `--sport`/`--dport` choice never fired and every rule got
    `--dport`;
  * the backward policy of `<-->` looked the service up on the reverse role
    (`Error: Service host2.S350 is unknown.`), because a service is offered by
    the server side and the reverse role is the client.

Neither `--->` nor `<-->` is used with a service by any workload in the tree --
`wl_up`, `wl_ifi` and `wl_example` use the service-less form -- which is why all
three sat undisturbed. See CLOUD_BENCH_PLAN.md §1.9.1/§1.9.2.
"""

import unittest

from policy import Policy
from policy_builder import PolicyBuilder


def _policy_with_service():
    policy = Policy()
    policy.add_service("S350")
    policy.services["S350"].add_attribute("protocol", "'tcp'")
    policy.services["S350"].add_attribute("port", "350")
    policy.add_role("client")
    policy.add_role("server")
    policy.roles["server"].add_service("S350")
    return policy


class TestProviderIsPartOfTheServiceCondition(unittest.TestCase):

    def setUp(self):
        self.policy = _policy_with_service()

    def test_the_forward_condition_carries_provider_and_the_attributes_together(self):
        """ One condition, not two. `to_iptables` reads `provider` and `port`
        off the SAME dict, so splitting them disables its direction choice. """
        self.policy.add_reachability_policy(
            "client", "server", "S350", condition={"provider": "server"})
        conditions = self.policy.policies[("client", "server")].conditions

        self.assertEqual(len(conditions), 1)
        self.assertEqual(
            conditions[0],
            {"provider": "server", "protocol": "tcp", "port": 350})

    def test_a_service_less_condition_is_still_its_own_operand(self):
        """ `<->>`'s backward state condition has no service to merge into and
        must keep working. """
        self.policy.add_reachability_policy(
            "server", "client", condition={"state": "RELATED,ESTABLISHED"})
        conditions = self.policy.policies[("server", "client")].conditions

        self.assertEqual(conditions, [{"state": "RELATED,ESTABLISHED"}])

    def test_the_service_is_looked_up_on_the_PROVIDER_not_the_target(self):
        """ The backward direction of `<-->`: from server to client, with the
        service still the server's. Looking it up on `client` is what raised
        `Error: Service ... is unknown.` """
        self.policy.add_reachability_policy(
            "server", "client", "S350", condition={"provider": "server"})

        self.assertTrue(self.policy.policy_exists("server", "client"))

    def test_an_unknown_service_on_the_provider_still_raises(self):
        from policy_exceptions import ServiceUnknownException
        self.policy.add_service("S999")

        with self.assertRaises(ServiceUnknownException):
            self.policy.add_reachability_policy(
                "client", "server", "S999", condition={"provider": "server"})

    def test_without_a_provider_the_target_still_owns_the_service(self):
        """ `<->>` passes no provider; its forward lookup is unchanged. """
        self.policy.add_reachability_policy("client", "server", "S350")
        conditions = self.policy.policies[("client", "server")].conditions

        self.assertEqual(conditions, [{"protocol": "tcp", "port": 350}])


class TestTheCsvResolvesTheDirection(unittest.TestCase):
    """ `provider` is internal. The CSV carries the resolved field instead, so
    its consumers need no notion of who offers what. """

    def setUp(self):
        self.policy = _policy_with_service()

    def _cell(self, csv, role_from, role_to):
        rows = [r.split(',') for r in csv.strip().split('\n')]
        header = rows[0]
        for row in rows[1:]:
            if row[0] == role_from:
                return row[header.index(role_to)]
        raise AssertionError("no row for %s" % role_from)

    def test_the_forward_cell_uses_the_destination_port(self):
        self.policy.add_reachability_policy(
            "client", "server", "S350", condition={"provider": "server"})

        self.assertEqual(
            self._cell(self.policy.roles_to_csv(), "client", "server"),
            "(protocol:tcp;port:350)")

    def test_the_backward_cell_uses_the_SOURCE_port(self):
        """ The swap. Server to client, on the service the server offers, is
        return traffic: it is identified by its source port. """
        self.policy.add_reachability_policy(
            "server", "client", "S350", condition={"provider": "server"})

        self.assertEqual(
            self._cell(self.policy.roles_to_csv(), "server", "client"),
            "(protocol:tcp;sport:350)")

    def test_provider_never_reaches_the_csv(self):
        self.policy.add_reachability_policy(
            "client", "server", "S350", condition={"provider": "server"})

        self.assertNotIn("provider", self.policy.roles_to_csv())


class TestTheOperatorsEndToEnd(unittest.TestCase):
    """ Through PolicyBuilder, which is where the operator semantics live. """

    INVENTORY = """
describe service S350
    protocol = 'tcp'
    port = 350
end

describe role client
end

describe role server
    offers S350
end
"""

    def _build(self, rule):
        policy = Policy()
        PolicyBuilder.build(
            "%s\ndescribe policies (default: deny)\n    %s\nend\n" % (
                self.INVENTORY, rule),
            policy)
        return policy

    def test_bidirectional_with_a_service_compiles_and_swaps(self):
        policy = self._build("client <--> server.S350")
        csv = policy.roles_to_csv()

        self.assertIn("protocol:tcp;port:350", csv)
        self.assertIn("protocol:tcp;sport:350", csv)

    def test_unidirectional_with_a_service_emits_only_the_forward_cell(self):
        policy = self._build("client ---> server.S350")

        self.assertTrue(policy.policy_exists("client", "server"))
        self.assertFalse(policy.policy_exists("server", "client"))

    def test_no_check_condition_mentions_provider(self):
        policy = self._build("client <--> server.S350")

        self.assertNotIn("provider", policy.roles_to_csv())


if __name__ == '__main__':
    unittest.main()
