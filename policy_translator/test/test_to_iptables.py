#!/usr/bin/env python3

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

""" Block-wise unit tests for Policy.to_iptables().

    Per the concept (thesis Sec. 7.3, Algorithm 7.1), a generated rule set is a
    composition of mutually independent blocks emitted in a *fixed order*, and
    each block is single-action so the order of rules *within* a block has no
    impact on the filtering semantics. The generator marks block boundaries with
    "# === <name> ===" section-header comments (semantically inert, also a
    readability aid for human reviewers).

    These tests therefore assert:
      1. the block order is exactly the canonical order, and
      2. each block's rules match the expectation as an order-independent
         multiset (intra-block order is deliberately not constrained).
"""

import unittest

from collections import OrderedDict

from policy import Policy, Role, Superrole, Service, ReachabilityPolicy


# Section headers emitted by Policy.to_iptables(), in canonical order.
H_V4_DEFAULT = "# === IPv4 Default Policy ==="
H_V4_ANTISPOOF = "# === IPv4 Anti-Spoofing ==="
H_V4_STATE = "# === IPv4 State Tracking ==="
H_V6_DEFAULT = "# === IPv6 Default Policy ==="
H_V6_ANTISPOOF = "# === IPv6 Anti-Spoofing ==="
H_V6_ICMP = "# === IPv6 ICMP ==="
H_V6_HARDENING = "# === IPv6 Hardening ==="
H_V6_STATE = "# === IPv6 State Tracking ==="
H_ACCESS = "# === Access Rules ==="

CANON_ORDER = [
    H_V4_DEFAULT,
    H_V4_ANTISPOOF,
    H_V4_STATE,
    H_V6_DEFAULT,
    H_V6_ANTISPOOF,
    H_V6_ICMP,
    H_V6_HARDENING,
    H_V6_STATE,
    H_ACCESS,
]


def parse_blocks(rule_set):
    """ Splits a generated rule set into an ordered list of (header, [rules]).

    Header lines start with "# ==="; every other non-empty line is a rule that
    belongs to the most recently seen header.
    """
    blocks = []
    current = None
    for line in rule_set.splitlines():
        if not line:
            continue
        if line.startswith("# ==="):
            current = (line, [])
            blocks.append(current)
        else:
            assert current is not None, f"rule before any section header: {line!r}"
            current[1].append(line)
    return blocks


class TestToIptables(unittest.TestCase):

    """ Block-wise tests for the iptables generation of the Policy class. """

    def setUp(self):
        self.policy = Policy()
        self.policy.set_default_policy("deny")
        self.policy.add_role("Internal")
        self.policy.add_role("External")
        self.policy.roles["Internal"].add_attribute('ipv4', '"1.2.3.4"')
        self.policy.roles["External"].add_attribute('ipv4', '"4.3.2.1"')

        # Access-rule block; populated per test before calling check().
        self.access = []

    def expected_blocks(self, default):
        """ Expected blocks for the static part of the rule set given the default
        policy ("deny" or "allow"). The access block is filled from self.access.
        Only the default-rule target and access actions differ between deny and
        allow; the static middle blocks are identical.
        """
        target = "DROP" if default == "deny" else "ACCEPT"

        blocks = OrderedDict()
        blocks[H_V4_DEFAULT] = [f"iptables -P FORWARD {target}"]
        blocks[H_V4_ANTISPOOF] = [
            "iptables -A FORWARD -i eth1 -s 1.2.3.4 -j DROP",
            "iptables -A FORWARD -i eth1 -s 4.3.2.1 -j DROP",
        ]
        blocks[H_V4_STATE] = [
            "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT",
        ]
        blocks[H_V6_DEFAULT] = [f"ip6tables -P FORWARD {target}"]
        # No role carries an IPv6 attribute in these tests -> empty block.
        blocks[H_V6_ANTISPOOF] = []
        blocks[H_V6_ICMP] = [
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT",
        ]
        blocks[H_V6_HARDENING] = [
            "ip6tables -N routinghdr",
            "ip6tables -A routinghdr -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP",
            "ip6tables -A routinghdr -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP",
            "ip6tables -A routinghdr -m rt --rt-type 0 --rt-segsleft 0 -j RETURN",
            "ip6tables -A routinghdr -m rt --rt-type 2 --rt-segsleft 1 -j RETURN",
            "ip6tables -A routinghdr -m rt ! --rt-segsleft 0 --j DROP",
            "ip6tables -A FORWARD -m ipv6header --header ipv6-route --soft -j routinghdr",
        ]
        blocks[H_V6_STATE] = [
            "ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT",
        ]
        blocks[H_ACCESS] = list(self.access)
        return blocks

    # -- tests ---------------------------------------------------------------

    def test_defaultPolicieDeny(self):
        self.check("deny")

    def test_defaultPolicieAllow(self):
        self.policy.set_default_policy("allow")
        self.check("allow")

    def test_internet(self):
        self.policy.add_reachability_policy("Internet", "Internal")
        self.access += [
            "iptables -t raw -A PREROUTING -i eth1 -d 1.2.3.4 -m comment --comment \"Internet to Internal\" -j NOTRACK",
            "iptables -A FORWARD -i eth1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internet to Internal\" -j ACCEPT",
        ]
        self.check("deny")

    def test_simplePolicy(self):
        self.policy.add_reachability_policy("Internal", "External")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT",
        ]
        self.check("deny")

    def test_relatedPolicy(self):
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.add_reachability_policy("External", "Internal", condition={"state": "RELATED,ESTABLISHED"})
        self.access += [
            "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW -m comment --comment \"Internal to External\" -j ACCEPT",
        ]
        self.check("deny")

    def test_reversePolicy(self):
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.add_reachability_policy("External", "Internal")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT",
            "iptables -t raw -A PREROUTING -s 4.3.2.1 -d 1.2.3.4 -m comment --comment \"External to Internal\" -j NOTRACK",
            "iptables -A FORWARD -s 4.3.2.1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"External to Internal\" -j ACCEPT",
        ]
        self.check("deny")

    def test_defaultallowsimple(self):
        self.policy.set_default_policy("allow")
        self.policy.add_reachability_policy("Internal", "External")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j DROP",
        ]
        self.check("allow")

    def test_defaulallowrevrerse(self):
        self.policy.set_default_policy("allow")
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.add_reachability_policy("External", "Internal")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j DROP",
            "iptables -t raw -A PREROUTING -s 4.3.2.1 -d 1.2.3.4 -m comment --comment \"External to Internal\" -j NOTRACK",
            "iptables -A FORWARD -s 4.3.2.1 -d 1.2.3.4 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"External to Internal\" -j DROP",
        ]
        self.check("allow")

    def test_defaultallowoneway(self):
        self.policy.set_default_policy("allow")
        self.policy.add_reachability_policy("Internal", "External", condition={"state": "NEW,INVALID"})
        self.access += [
            "iptables -A FORWARD -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW -m comment --comment \"Internal to External\" -j DROP",
        ]
        self.check("allow")

    def test_vlan(self):
        self.policy.add_reachability_policy("Internal", "External")
        self.policy.roles["Internal"].add_attribute('interface', '"eth2"')
        self.policy.roles["Internal"].add_attribute('vlan', '"1"')
        self.policy.roles["External"].add_attribute('interface', '"eth2"')
        self.policy.roles["External"].add_attribute('vlan', '"2"')
        self.access += [
            "iptables -t raw -A PREROUTING -i eth2.1 -s 1.2.3.4 -o eth2.2 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD -i eth2.1 -s 1.2.3.4 -o eth2.2 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT",
        ]
        self.check("deny")

    def test_service(self):
        cond = {"protocol": "tcp", "port": "80"}
        self.policy.add_reachability_policy("Internal", "External", condition=cond)
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '"80"')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTP")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD --protocol tcp --dport 80 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT",
        ]
        self.check("deny")

    def test_multipleServices(self):
        self.policy.add_service("HTTP")
        self.policy.services["HTTP"].add_attribute('port', '"80"')
        self.policy.services["HTTP"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTP")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD --protocol tcp --dport 80 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT",
        ]

        self.policy.add_service("HTTPS")
        self.policy.services["HTTPS"].add_attribute('port', '"443"')
        self.policy.services["HTTPS"].add_attribute('protocol', '"tcp"')
        self.policy.roles["External"].add_service("HTTPS")
        self.policy.add_reachability_policy("Internal", "External", service_to="*")
        self.access += [
            "iptables -t raw -A PREROUTING -s 1.2.3.4 -d 4.3.2.1 -m comment --comment \"Internal to External\" -j NOTRACK",
            "iptables -A FORWARD --protocol tcp --dport 443 -s 1.2.3.4 -d 4.3.2.1 -m conntrack --ctstate NEW,NOTRACK -m comment --comment \"Internal to External\" -j ACCEPT",
        ]
        self.check("deny")

    # -- helper --------------------------------------------------------------

    def check(self, default):
        expected = self.expected_blocks(default)
        actual = parse_blocks(self.policy.to_iptables())

        # 1. block order is fixed and correct (no missing/extra/interleaved blocks)
        self.assertEqual([header for header, _ in actual], list(expected.keys()))

        # 2. each block's rules match as an order-independent multiset
        for header, rules in actual:
            self.assertCountEqual(
                rules, expected[header], msg=f"rule mismatch in block {header}"
            )


if __name__ == '__main__':
    unittest.main()
