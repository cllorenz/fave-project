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

""" The builtin `Internet` role offers every DECLARED service.

WHY. The Internet lies outside the administrative boundary of whoever writes the
policy, so its service offerings cannot be enumerated or restricted -- a rule
naming a service on the Internet side should not have to declare that the
Internet "offers" it. Until now `Internet` was created with an `interface`
attribute and no services at all, so `Internet.HTTP` raised
ServiceUnknownException and `Internet.*` expanded to nothing.

WHY *DECLARED*, and not "anything at all" (owner decision 2026-09-18). A service
carries its attributes from the inventory, not from its name: the conditions a
rule compiles to come from `Policy.services[name].attributes`. If a service did
not have to be declared, those attributes could only come from a table of
well-known names -- and then HTTP would always mean port 80, so an HTTP service
on port 123 would be unsayable, and a custom service (ABC on tcp/1234) could not
be expressed at all. Requiring the declaration keeps every compliance-relevant
service explicit in the inventory; `Internet.*` then picks exactly those up.

This does NOT make `<-->` with a service work in general -- see
CLOUD_BENCH_PLAN.md §1.9.2. It removes the Internet-shaped instance of that
problem; the host-to-host instance needs the reverse-direction swap.
"""

import unittest

from policy import Policy


class TestInternetOffersDeclaredServices(unittest.TestCase):

    def setUp(self):
        self.policy = Policy()
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute("protocol", "'tcp'")
        self.policy.services["HTTP"].add_attribute("port", "80")

    def test_the_internet_offers_a_declared_service(self):
        self.assertTrue(self.policy.roles["Internet"].offers_service("HTTP"))

    def test_the_internet_does_not_offer_an_UNdeclared_service(self):
        """ The point of choosing "declared" over "anything": a service that was
        never declared has no attributes to compile to, so accepting it would
        mean inventing them from the name. """
        self.assertFalse(self.policy.roles["Internet"].offers_service("GOPHER"))

    def test_a_service_declared_later_is_still_offered(self):
        """ Declaration order must not matter -- the inventory is read before
        the policy, but nothing enforces the order within it. """
        self.policy.add_service("ABC")
        self.assertTrue(self.policy.roles["Internet"].offers_service("ABC"))

    def test_the_internet_reports_that_it_offers_services(self):
        self.assertTrue(self.policy.roles["Internet"].offers_services())

    def test_an_internet_with_no_declared_services_offers_none(self):
        empty = Policy()
        self.assertFalse(empty.roles["Internet"].offers_services())
        self.assertFalse(empty.roles["Internet"].offers_service("HTTP"))

    def test_the_wildcard_expands_to_every_declared_service(self):
        self.policy.add_service("ABC")
        services = self.policy.roles["Internet"].get_services()["Internet"]

        self.assertEqual(sorted(services), ["ABC", "HTTP"])

    def test_an_ordinary_role_still_offers_only_what_it_declares(self):
        """ The guard that keeps this from becoming "every role offers
        everything" -- which would make the inventory's `offers` meaningless. """
        self.policy.add_role("WebServer")
        self.assertFalse(self.policy.roles["WebServer"].offers_service("HTTP"))

        self.policy.roles["WebServer"].add_service("HTTP")
        self.assertTrue(self.policy.roles["WebServer"].offers_service("HTTP"))

    def test_an_ordinary_roles_wildcard_is_unaffected(self):
        self.policy.add_role("WebServer")
        self.policy.roles["WebServer"].add_service("HTTP")
        self.policy.add_service("ABC")

        services = self.policy.roles["WebServer"].get_services()["WebServer"]
        self.assertEqual(sorted(services), ["HTTP"])


class TestServiceAttributesComeFromTheInventory(unittest.TestCase):
    """ The substance of the owner's argument, pinned: a service's meaning is
    its declaration, never its name. """

    def test_a_well_known_name_may_carry_an_unusual_port(self):
        policy = Policy()
        policy.add_service("HTTP")
        policy.services["HTTP"].add_attribute("protocol", "'tcp'")
        policy.services["HTTP"].add_attribute("port", "123")

        self.assertTrue(policy.roles["Internet"].offers_service("HTTP"))
        self.assertEqual(policy.services["HTTP"].attributes["port"], 123)

    def test_a_custom_service_is_expressible(self):
        policy = Policy()
        policy.add_service("ABC")
        policy.services["ABC"].add_attribute("protocol", "'tcp'")
        policy.services["ABC"].add_attribute("port", "1234")

        self.assertTrue(policy.roles["Internet"].offers_service("ABC"))
        self.assertEqual(policy.services["ABC"].attributes["port"], 1234)


class TestReachabilityPolicyWithAnInternetService(unittest.TestCase):
    """ The end-to-end effect: a rule naming a service on the Internet side now
    resolves instead of raising. """

    def setUp(self):
        self.policy = Policy()
        self.policy.add_service("S332")
        self.policy.services["S332"].add_attribute("protocol", "'tcp'")
        self.policy.services["S332"].add_attribute("port", "332")
        self.policy.add_role("host20")
        self.policy.roles["host20"].add_service("S332")

    def test_a_backward_policy_naming_the_service_on_the_internet_resolves(self):
        """ This is the shape `<-->` builds for its backward direction:
        add_reachability_policy(role_to, role_from, service_to). With the
        original source being Internet, it used to raise. """
        self.policy.add_reachability_policy("host20", "Internet", "S332")

        self.assertTrue(self.policy.policy_exists("host20", "Internet"))

    def test_the_condition_carries_the_declared_attributes(self):
        self.policy.add_reachability_policy("host20", "Internet", "S332")
        conditions = self.policy.policies[("host20", "Internet")].conditions

        self.assertIn({"protocol": "tcp", "port": 332}, conditions)


if __name__ == '__main__':
    unittest.main()
