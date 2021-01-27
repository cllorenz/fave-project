#!/usr/bin/env python2

""" This module provides unit tests for the Policy, Role, Superrole, Service,
    and ReachabilityPolicy classes.
"""

import unittest

from policy import Policy, Role, Superrole, Service, ReachabilityPolicy

class TestToIptables(unittest.TestCase):

    """ This class provides unit tests for the Policy class.
    """
    exp = []

    def setUp(self):
        self.policy = Policy()
        self.policy.set_default_policy("deny")
        self.policy.add_role("Internal")
        self.policy.add_role("External")
        self.policy.roles["Internal"].add_attribute('ipv4', '"1.2.3.4"')
        self.policy.roles["External"].add_attribute('ipv4', '"4.3.2.1"')

        rule = "iptables -P FORWARD DROP"
        self.exp.append(rule)
        rule = "ip6tables -P FORWARD DROP"
        self.exp.append(rule)
        rule = "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        self.exp.append(rule)

    def tearDown(self):
        TestToIptables.exp = []
        del self.policy

    def test_defaultPolicies(self):
        #testing default ruleset for deny
        self.check(self.exp)

        #testing default ruleset for allow
        self.policy.set_default_policy("allow")
        self.exp = []
        rule = "iptables -P FORWARD ACCEPT"
        self.exp.append(rule)
        rule = "ip6tables -P FORWARD ACCEPT"
        self.exp.append(rule)
        rule = "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        self.exp.append(rule)
        self.check(self.exp)

    def test_internet(self):
        # Test Internet
        self.policy.add_reachability_policy("Internet", "Internal")
        rule = "iptables -t raw -A PREROUTING -i eth1 -d 1.2.3.4 -m comment --comment \"Internet to Internal\" -j NOTRACK"
        self.exp.append(rule)
        rule = "iptables -A FORWARD -i eth1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internet to Internal\" -j ACCEPT"
        self.exp.append(rule)
        self.check(self.exp)


    def test_simplePolicy(self):
        # simple policy test
        self.policy.add_reachability_policy("Internal", "External")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.exp.append(rule)
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.exp.append(rule)
        self.check(self.exp)

    def test_vlan(self):
        self.policy.add_reachability_policy("Internal", "External")
        # Vlan test
        self.policy.roles["Internal"].add_attribute('vlan', '"1"')
        self.policy.roles["External"].add_attribute('vlan', '"2"')
        rule = "iptables -t raw -A PREROUTING -i eth2.1 -s 1.2.3.4 -o eth2.2 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.exp.append(rule)

        rule = "iptables -A FORWARD -i eth2.1 -s 1.2.3.4 -o eth2.2 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.exp.append(rule)
        self.check(self.exp)
#TODO services and multiple services add serv to cond
    def test_service(self):
        # Service test
        cond = {
            "protocol": "tcp",
            "port": "80"
        }
        self.policy.add_reachability_policy("Internal", "External", condition=cond)
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '"80"')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTP")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.exp.append(rule)
        rule = "iptables -A FORWARD --protocol tcp --dport 80 --sport 80 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.exp.append(rule)
        self.check(self.exp)

    def test_multipleServices(self):
        # Multiple Services test

        cond = [{"protocol": "tcp", "port": "80"}, {"protocol": "tcp", "port": "443"}]
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '"80"')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTP")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.exp.append(rule)
        rule = "iptables -A FORWARD --protocol tcp --dport 80 --sport 80 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.exp.append(rule)

        self.policy.add_service("HTTPS")
        self.policy.services["HTTPS"].add_attribute('port', '"443"')
        self.policy.services["HTTPS"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTPS")
        self.policy.add_reachability_policy("Internal", "External", service_to="*")

        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.exp.append(rule)
        rule = "iptables -A FORWARD --protocol tcp --dport 443 --sport 443 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.exp.append(rule)
        self.check(self.exp)

    def check(self, exp):
        x = "\n".join(str(e) for e in exp)
        res = self.policy.to_iptables()
        self.assertEqual(res, x)

if __name__ == '__main__':
    unittest.main()