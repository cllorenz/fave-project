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

""" This module provides unit tests for the Policy, Role, Superrole, Service,
    and ReachabilityPolicy classes.
"""

import unittest

from policy import Policy, Role, Superrole, Service, ReachabilityPolicy

class TestPolicy(unittest.TestCase):

    """ This class provides unit tests for the Policy class.
    """

    def setUp(self):
        self.policy = Policy()


    def tearDown(self):
        del self.policy


    def test_add_role(self):

        """ Add a role to the policy.
        """

        self.policy.add_role("WebService")
        self.assertTrue(self.policy.role_exists("WebService"))


    def test_add_superrole(self):

        """ Add a superrole to the policy consisting of WebService and
            NameService roles.
        """

        self.test_add_service()

        self.policy.add_role("NameService")
        self.policy.add_service("DNS")
        self.policy.services["DNS"].add_attribute('port', '53')
        self.policy.services["DNS"].add_attribute('protocol', '"udp"')
        self.policy.roles["NameService"].add_service("DNS")

        self.policy.add_superrole("Services")
        self.policy.roles["Services"].add_subrole("WebService")
        self.policy.roles["Services"].add_subrole("NameService")

        exp_http = Service(
            "HTTP",
            self.policy,
            attributes={'port' : 80, 'protocol' : 'tcp'}
        )

        exp_web = Role(
            "WebService",
            self.policy,
            services={"HTTP" : exp_http}
        )

        exp_dns = Service(
            "DNS",
            self.policy,
            attributes={'port' : 53, 'protocol' : 'udp'}
        )

        exp_name = Role(
            "NameService",
            self.policy,
            services={"DNS" : exp_dns}
        )

        exp = {
            "Services" : Superrole(
                "Services",
                self.policy,
                subroles={"WebService" : exp_web, "NameService" : exp_name},
                subservices={"WebService" : {}, "NameService" : {}}
            ),
            "WebService" : exp_web,
            "NameService" : exp_name,
            "Internet" : Role("Internet", self.policy, attributes={'interface': 'fw.generic.eth1'})
        }

        self.assertEqual(self.policy.roles.keys(), exp.keys())

        for key in exp:
            self.assertEqual(self.policy.roles[key], exp[key])


    def test_add_service(self):

        """ Add an HTTP service to a WebService role.
        """

        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '80')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')

        self.test_add_role()
        self.policy.roles["WebService"].add_service("HTTP")

        self.assertTrue(self.policy.service_exists("HTTP"))


    def test_role_exists(self):

        """ Check if the WebService role exists.
        """

        self.assertFalse(self.policy.role_exists("WebService"))
        self.test_add_role()
        self.assertTrue(self.policy.role_exists("WebService"))


    def test_service_exists(self):

        """ Check if the HTTP service exists.
        """

        self.assertFalse(self.policy.service_exists("HTTP"))
        self.test_add_service()
        self.assertTrue(self.policy.service_exists("HTTP"))


    def test_policy_exists(self):

        """ Check if a policy from the Internet to a WebService exists.
        """

        self.assertFalse(self.policy.policy_exists("Internet", "WebService"))
        self.test_add_service()
        self.policy.add_reachability_policy("Internet", "WebService")
        self.assertTrue(self.policy.policy_exists("Internet", "WebService"))


    def test_add_reachability_policy(self):

        """ Add a policy to allow traffic from a WebService to the Internet.
        """

        self.test_policy_exists()
        self.policy.add_reachability_policy("WebService", "Internet")
        self.assertTrue(self.policy.policy_exists("WebService", "Internet"))


    def test_set_default_policy(self):

        """ Test toggling the default policy (i.e., allow and deny).
        """

        self.assertFalse(self.policy.default_policy)
        self.policy.set_default_policy("allow")
        self.assertTrue(self.policy.default_policy)
        self.policy.set_default_policy("deny")
        self.assertFalse(self.policy.default_policy)

class TestRole(unittest.TestCase):

    """ This class provides unit tests for the Role class.
    """

    def setUp(self):
        self.role = Role("WebService", Policy())


    def tearDown(self):
        del self.role


    def test_add_attribute(self):

        """ Test adding a VLAN tag.
        """

        self.role.add_attribute("vlan", "23")

        exp = Role("WebService", Policy(), attributes={"vlan" : 23})

        self.assertEqual(self.role, exp)


    def test_add_service(self):

        """ Test adding an HTTP service.
        """

        self.role.policy.add_service("HTTP")
        self.role.add_service("HTTP")

        exp = Role(
            "WebService",
            Policy(),
            services={"HTTP" : self.role.policy.services["HTTP"]}
        )

        self.assertEqual(self.role, exp)


    def test_get_roles(self):

        """ Test getting existing roles.
        """

        self.assertEqual(self.role.get_roles(), ["WebService"])


    def test_get_services(self):

        """ Test getting all existing services.
        """

        self.assertEqual(self.role.get_services(), {"WebService" : {}})

        self.test_add_service()

        self.assertEqual(
            self.role.get_services(),
            {"WebService" : {"HTTP" : self.role.policy.services["HTTP"]}}
        )


    def test_offers_services(self):

        """ Check whether any services are offered.
        """

        self.assertFalse(self.role.offers_services())
        self.test_add_service()
        self.assertTrue(self.role.offers_services())

    def test_offers_service(self):

        """ Check whether the HTTP service is offered
        """

        self.assertFalse(self.role.offers_service("HTTP"))
        self.test_add_service()
        self.assertTrue(self.role.offers_service("HTTP"))


class TestSuperrole(unittest.TestCase):

    """ This class provides unit tests for the Superrole class.
    """

    def setUp(self):
        self.superrole = Superrole("Services", Policy())


    def tearDown(self):
        del self.superrole


    def test_add_attribute(self):

        """ Test adding a VLAN tag.
        """

        self.test_add_subrole()
        self.superrole.add_attribute("vlan", "1")

        exp = Superrole(
            "Services",
            self.superrole.policy,
            subroles={
                "WebService" : Role(
                    "WebService",
                    self.superrole.policy,
                    attributes={"vlan" : 1}
                )
            },
            subservices={"WebService" : {}}
        )

        self.assertEqual(self.superrole, exp)


    def test_add_subrole(self):

        """ Test adding a WebService role as sub role.
        """

        self.superrole.policy.add_role("WebService")

        self.superrole.add_subrole("WebService")

        exp = Superrole(
            "Services",
            self.superrole.policy,
            subroles={"WebService" : Role("WebService", self.superrole.policy)},
            subservices={"WebService" : {}}
        )

        self.assertEqual(self.superrole, exp)


    def test_add_subservice(self):

        """ Test adding a NameService with a DNS service as a sub role.
        """

        self.superrole.policy.add_service("DNS")
        self.superrole.policy.services["DNS"].add_attribute('port', '53')
        self.superrole.policy.services["DNS"].add_attribute('protocol', '"udp"')

        self.test_add_service()

        self.superrole.policy.add_role("NameService")
        self.superrole.add_subrole("NameService")

        self.superrole.subroles["NameService"].add_service("DNS")

        self.superrole.add_subservice("NameService", "DNS")

        exp_http = Service(
            "HTTP",
            self.superrole.policy,
            attributes={'port' : 80, 'protocol' : 'tcp'}
        )

        exp_dns = Service(
            "DNS",
            self.superrole.policy,
            attributes={'port' : 53, 'protocol' : 'udp'}
        )

        exp = Superrole(
            "Services",
            self.superrole.policy,
            subroles={
                "WebService" : Role(
                    "WebService",
                    self.superrole.policy,
                    services={"HTTP" : exp_http}
                ),
                "NameService" : Role(
                    "NameService",
                    self.superrole.policy,
                    services={"DNS" : exp_dns}
                )
            },
            subservices={
                "WebService" : {"HTTP" : exp_http},
                "NameService" : {"DNS" : exp_dns}
            }
        )

        self.assertEqual(self.superrole, exp)


    def test_add_service(self):

        """ Test adding an HTTP service to all sub roles.
        """

        self.superrole.policy.add_service("HTTP")
        self.superrole.policy.services["HTTP"].add_attribute('port', '80')
        self.superrole.policy.services["HTTP"].add_attribute('protocol', '"tcp"')

        self.test_add_subrole()

        self.superrole.add_service("HTTP")

        exp_srv = Service(
            "HTTP",
            self.superrole.policy,
            attributes={'port' : 80, 'protocol' : 'tcp'}
        )
        exp = Superrole(
            "Services",
            self.superrole.policy,
            subroles={
                "WebService" : Role(
                    "WebService",
                    self.superrole.policy,
                    services={"HTTP" : exp_srv}
                )
            },
            subservices={"WebService" : {"HTTP" : exp_srv}}
        )

        self.assertEqual(self.superrole, exp)


    def test_get_roles(self):

        """ Test getting all sub roles.
        """

        self.assertEqual(self.superrole.get_roles(), [])
        self.test_add_subrole()
        self.assertEqual(self.superrole.get_roles(), ["WebService"])


    def test_get_services(self):

        """ Test getting all sub services.
        """

        self.assertEqual(self.superrole.get_services(), {})

        self.test_add_service()

        self.assertEqual(
            self.superrole.get_services(),
            {
                "WebService" : {
                    "HTTP" : Service(
                        "HTTP",
                        self.superrole.policy,
                        attributes={'port' : 80, 'protocol' : 'tcp'}
                    )
                }
            }
        )


    def test_offers_services(self):

        """ Check whether any services are offered by the superrole directly.
        """

        self.assertFalse(self.superrole.offers_services())
        self.test_add_service()
        self.assertFalse(self.superrole.offers_services())


    def test_offers_service(self):

        """ Check whether the HTTP service is offered by the superrole directly.
        """

        self.assertFalse(self.superrole.offers_service("HTTP"))
        self.test_add_service()
        self.assertFalse(self.superrole.offers_service("HTTP"))


class TestAbstractRole(unittest.TestCase):


    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_add_attribute(self):
        pass

    def test_add_service(self):
        pass

    def test_add_subrole(self):
        pass

    def test_get_roles(self):
        pass

    def test_get_services(self):
        pass

    def test_offers_service(self):
        pass

    def test_offers_services(self):
        pass


class TestService(unittest.TestCase):

    """ This class provides unit tests for the Service class.
    """

    def test_add_attribute(self):

        """ Test adding attributes an HTTP service.
        """

        res_policy = Policy()
        res = Service("HTTP", res_policy)
        res.add_attribute("port", "80")
        res.add_attribute("protocol", "\"tcp\"")

        exp_policy = Policy()
        exp = Service(
            "HTTP", exp_policy, attributes={'port' : 80, 'protocol' : 'tcp'}
        )

        self.assertEqual(res, exp)


class TestReachabilityPolicy(unittest.TestCase):

    """ This class provides unit tests for the ReachablityPolicy class.
    """

    def test_update_conditions(self):

        """ Test updating the set of reachability conditions from the Internet
            to the WebService to allow responses for related or established
            connections.
        """

        res_policy = Policy()
        res = ReachabilityPolicy(
            "Internet",
            "WebService",
            res_policy,
            conditions=[{"service" : "HTTP"}]
        )
        res.update_conditions([
            {"state": "RELATED,ESTABLISHED"}, {"service" : "HTTP"}
        ])

        exp_policy = Policy()
        exp = ReachabilityPolicy(
            "Internet",
            "WebService",
            exp_policy,
            conditions=[{"service" : "HTTP"}, {"state": "RELATED,ESTABLISHED"}]
        )

        self.assertEqual(res, exp)


if __name__ == '__main__':
    unittest.main()
