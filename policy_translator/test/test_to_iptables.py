#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2021 Benjamin Plewka
# List of co-authors:
#    Claas Lorenz <claas_lorenz@genua.de>

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

class TestToIptables(unittest.TestCase):

    """ This class provides unit tests for the Policy class.
    """
    def setUp(self):
        self.exp = []
        self.expallow = []
        self.expdeny = []
        self.policy = Policy()
        self.policy.set_default_policy("deny")
        self.policy.add_role("Internal")
        self.policy.add_role("External")
        self.policy.roles["Internal"].add_attribute('ipv4', '"1.2.3.4"')
        self.policy.roles["External"].add_attribute('ipv4', '"4.3.2.1"')

        rule = "iptables -P FORWARD DROP"
        self.expdeny.append(rule)
        rule = "iptables -P FORWARD ACCEPT"
        self.expallow.append(rule)

        rule = "iptables -A FORWARD -i eth1 -s 1.2.3.4 -j DROP"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD -i eth1 -s 4.3.2.1 -j DROP"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)

        #ipv6
        rule = "ip6tables -P FORWARD DROP"
        self.expdeny.append(rule)
        rule = "ip6tables -P FORWARD ACCEPT"
        self.expallow.append(rule)

        #ICMP Traffic
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)

        #Routing-Header
        rule = "ip6tables -N routinghdr"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A routinghdr -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A routinghdr -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A routinghdr -m rt --rt-type 0 --rt-segsleft 0 -j RETURN"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A routinghdr -m rt --rt-type 2 --rt-segsleft 1 -j RETURN"
        self.expallow.append(rule)
        self.expdeny.append(rule)
        rule = "ip6tables -A routinghdr -m rt ! --rt-segsleft 0 --j DROP"
        self.expallow.append(rule)
        self.expdeny.append(rule)

        rule = "ip6tables -A FORWARD -m ipv6header --header ipv6-route --soft -j routinghdr"
        self.expallow.append(rule)
        self.expdeny.append(rule)

        rule = "ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        self.expallow.append(rule)
        self.expdeny.append(rule)

    def test_defaultPolicieDeny(self):
        #testing default ruleset for deny
        self.check(self.expdeny)

    def test_defaultPolicieAllow(self):
        self.policy.set_default_policy("allow")
        #testing default ruleset for allow
        self.check(self.expallow)

    def test_internet(self):
        # Test Internet
        self.policy.add_reachability_policy("Internet", "Internal")
        rule = "iptables -t raw -A PREROUTING -i eth1 -d 1.2.3.4 -m comment --comment \"Internet to Internal\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD -i eth1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internet to Internal\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)


    def test_simplePolicy(self):
        # simple policy test
        self.policy.add_reachability_policy("Internal", "External")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)

    def test_relatedPolicy(self):
        # simple policy test
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.add_reachability_policy("External", "Internal", condition={"state": "RELATED,ESTABLISHED"})
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)

    def test_reversePolicy(self):
        # simple policy test
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.add_reachability_policy("External", "Internal")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)
        rule = "iptables -t raw -A PREROUTING -s 4.3.2.1 -d 1.2.3.4 -m comment --comment \"External to Internal\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD -s 4.3.2.1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"External to Internal\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)

    def test_defaultallowsimple(self):
        self.policy.set_default_policy("allow")
        self.policy.add_reachability_policy("Internal", "External")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expallow.append(rule)
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j DROP"
        self.expallow.append(rule)
        self.check(self.expallow)

    def test_defaulallowrevrerse(self):
        self.policy.set_default_policy("allow")
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.add_reachability_policy("External", "Internal")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expallow.append(rule)
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j DROP"
        self.expallow.append(rule)
        rule = "iptables -t raw -A PREROUTING -s 4.3.2.1 -d 1.2.3.4 -m comment --comment \"External to Internal\" -j NOTRACK"
        self.expallow.append(rule)
        rule = "iptables -A FORWARD -s 4.3.2.1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"External to Internal\" -j DROP"
        self.expallow.append(rule)
        self.check(self.expallow)

    def test_defaultallowoneway(self):
        self.policy.set_default_policy("allow")
        self.policy.add_reachability_policy("Internal", "External", condition={"state": "NEW,INVALID"})
        rule = "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW -m comment --comment \"Internal to External\" -j DROP"
        self.expallow.append(rule)
        self.check(self.expallow)

    def test_vlan(self):
        self.policy.add_reachability_policy("Internal", "External")
        # Vlan test
        self.policy.roles["Internal"].add_attribute('interface', '"eth2"')
        self.policy.roles["Internal"].add_attribute('vlan', '"1"')
        self.policy.roles["External"].add_attribute('interface', '"eth2"')
        self.policy.roles["External"].add_attribute('vlan', '"2"')

        rule = "iptables -t raw -A PREROUTING -i eth2.1 -s 1.2.3.4 -o eth2.2 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expdeny.append(rule)

        rule = "iptables -A FORWARD -i eth2.1 -s 1.2.3.4 -o eth2.2 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)

    def test_service(self):
        # Service test
        cond = {"protocol": "tcp", "port": "80"}
        self.policy.add_reachability_policy("Internal", "External", condition=cond)
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '"80"')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTP")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD --protocol tcp --dport 80 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)

    def test_multipleServices(self):
        # Multiple Services test

        cond = [{"protocol": "tcp", "port": "80"}, {"protocol": "tcp", "port": "443"}]
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '"80"')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTP")
        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD --protocol tcp --dport 80 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)

        self.policy.add_service("HTTPS")
        self.policy.services["HTTPS"].add_attribute('port', '"443"')
        self.policy.services["HTTPS"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTPS")
        self.policy.add_reachability_policy("Internal", "External", service_to="*")

        rule = "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK"
        self.expdeny.append(rule)
        rule = "iptables -A FORWARD --protocol tcp --dport 443 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT"
        self.expdeny.append(rule)
        self.check(self.expdeny)

    def check(self, exp):
        x = "\n".join(str(e) for e in exp) + "\n"
        res = self.policy.to_iptables()
        self.assertEqual(res, x)

if __name__ == '__main__':
    unittest.main()
