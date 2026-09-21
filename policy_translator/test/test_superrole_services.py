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

""" A superrole offers what IT declares, and that travels down (TODO item 19).

THE INVARIANT (owner decision 2026-09-21). A superrole may offer services, and
its services are propagated transitively to its subroles. A subrole's own
services are NOT reachable through the group: `R ---> SR.*` accesses only what
`SR` offers -- via its own `offers` lines, or via a superrole above `SR` that
propagated them down.

What was broken is narrower than it first looks. `Superrole.offers_service` was
`return False` unconditionally, so the guard in `add_reachability_policy`
rejected services the group DOES declare:

    All ---> All.ARP        ServiceUnknownException: Service All.ARP unbekannt.

over a `def role All` whose body reads `offers ARP`. That is
`examples/fml-paper-policy.txt`, the FML paper's own policy, and it could not
be compiled at all.

THE SECOND DEFECT IS THE DANGEROUS ONE and is independent of superroles. An
empty condition list is how FPL spells an UNCONDITIONAL rule, and
`ReachabilityPolicy.update_conditions` states that "the empty list overpowers
all other lists of conditions" -- so `Y.*` over a role offering nothing did not
merely fail to restrict its own rule, it ERASED the conditions an earlier rule
had set for the same pair. It is refused now (`NoServicesOfferedException`).

A THIRD, found while checking that propagation is transitive: `add_subrole`
handed an outer group the inner group's own `subservices` dict rather than a
copy, so `Outer.add_service` wrote through into `Mid` and `Mid.*` resolved to a
service `Mid` never declared -- a role's offering changing because something
else included it, which is the invariant failing sideways.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy
from policy_builder import PolicyBuilder
from policy_exceptions import NoServicesOfferedException, ServiceUnknownException


_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SERVICES = """
def service Telnet
    protocol = 'tcp'
    port = 23
end

def service HTTPS
    protocol = 'tcp'
    port = 443
end

def service SSH
    protocol = 'tcp'
    port = 22
end
"""

_MEMBERS = _SERVICES + """
def role Alpha
    description = 'first'
    hosts = ['a1']
    offers Telnet
    offers HTTPS
end

def role Beta
    description = 'second'
    hosts = ['b1']
    offers HTTPS
    offers SSH
end

def role Client
    description = 'a client'
    hosts = ['c1']
end
"""


def _build(text):
    policy = Policy(strict=True)
    PolicyBuilder.build(text, policy)
    return policy


def _group(body, rule='Client ---> Both.*'):
    return (_MEMBERS + "def role Both\n" + body + "end\n"
            + "\ndef policies (default: deny)\n    %s\nend\n" % rule)


def _ports(policy, role_from, role_to):
    return [c.get('port') for c in policy.policies[(role_from, role_to)].conditions]


class TestAGroupOffersOnlyWhatItDeclares(unittest.TestCase):

    def test_a_plain_include_gives_the_group_nothing(self):
        """ THE INVARIANT. `Alpha` offers two services and `Both` includes it;
        `Both` still offers none, so the rule is refused rather than answered
        with Alpha's list. """
        with self.assertRaises(NoServicesOfferedException) as caught:
            _build(_group("    includes Alpha\n    includes Beta\n"))

        self.assertIn('Both', str(caught.exception))

    def test_the_groups_own_offers_are_what_a_wildcard_reaches(self):
        policy = _build(_group(
            "    includes Alpha\n    includes Beta\n    offers HTTPS\n"))

        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [443])
        self.assertEqual(_ports(policy, 'Client', 'Beta'), [443])

    def test_a_named_include_is_the_explicit_way_in(self):
        """ `includes Alpha.HTTPS` names one of Alpha's services deliberately.
        The invariant refuses the automatic case, not the declared one. """
        policy = _build(_group("    includes Alpha.HTTPS\n    includes Beta.SSH\n"))

        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [443, 22])

    def test_an_explicit_wildcard_include_names_all_of_a_members_services(self):
        """ `includes Alpha.*` is the long form of naming them one by one, so
        it is a declaration by the group and not the automatic inheritance the
        invariant refuses.

        It is also the only reachable shape that offers ONE service through TWO
        members, which is what item 18's `dict.fromkeys` is for: HTTPS appears
        in both lists and must be emitted once, at its first position.
        """
        policy = _build(_group("    includes Alpha.*\n    includes Beta.*\n"))

        # Telnet, HTTPS from Alpha; HTTPS again from Beta -- dropped -- then SSH
        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [23, 443, 22])

    def test_a_service_named_on_the_group_resolves(self):
        """ `X ---> Superrole.SERVICE`, the form fml-paper-policy.txt uses.
        Used to raise for a service the group declares itself. """
        policy = _build(_group("    includes Alpha\n    offers Telnet\n",
                               rule='Client ---> Both.Telnet'))

        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [23])

    def test_a_service_the_group_does_not_declare_is_still_refused(self):
        """ The other side: making superroles offer services must not make
        them offer their members' services. `Alpha` offers Telnet; `Both` does
        not, so `Both.Telnet` is unknown. """
        with self.assertRaises(ServiceUnknownException):
            _build(_group("    includes Alpha\n", rule='Client ---> Both.Telnet'))


class TestServicesTravelDown(unittest.TestCase):

    _NESTED = """
def service HTTPS
    protocol = 'tcp'
    port = 443
end

def role Leaf
    description = 'a leaf'
    hosts = ['l1']
    offers SSH
end

def service SSH
    protocol = 'tcp'
    port = 22
end

def role Mid
    includes Leaf
end

def role Outer
    includes Mid
    offers HTTPS
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> %s
end
"""

    def test_a_groups_service_reaches_a_nested_member(self):
        """ TRANSITIVELY: `Outer` offers HTTPS, `Outer` includes `Mid`, `Mid`
        includes `Leaf`, so `Leaf` offers HTTPS as well as its own SSH. """
        policy = _build(self._NESTED % 'Leaf.*')

        self.assertEqual(sorted(_ports(policy, 'Client', 'Leaf')), [22, 443])

    def test_the_wildcard_over_the_group_stops_at_the_groups_own_services(self):
        """ The same network read from above: `Outer.*` is HTTPS alone. Leaf's
        own SSH went nowhere, which is the invariant's whole point. """
        policy = _build(self._NESTED % 'Outer.*')

        self.assertEqual(_ports(policy, 'Client', 'Leaf'), [443])

    def test_an_inner_group_does_not_gain_what_the_outer_one_declares(self):
        """ The aliasing. `Outer.add_service` wrote through a SHARED
        `subservices` dict into `Mid`, so `Mid.*` answered HTTPS although `Mid`
        declares nothing -- a role's offering changed because something else
        included it. """
        with self.assertRaises(NoServicesOfferedException) as caught:
            _build(self._NESTED % 'Mid.*')

        self.assertIn('Mid', str(caught.exception))


class TestAnEmptyWildcardIsRefused(unittest.TestCase):
    """ Independent of superroles: a `.*` over anything offering nothing. """

    _NO_SERVICES = """
def role Empty
    description = 'offers nothing'
    hosts = ['e1']
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> Empty.*
end
"""

    def test_a_wildcard_over_an_atomic_role_offering_nothing(self):
        with self.assertRaises(NoServicesOfferedException) as caught:
            _build(self._NO_SERVICES)

        self.assertIn('Empty', str(caught.exception))

    def test_the_refusal_does_not_reach_a_rule_naming_no_service(self):
        """ `Client ---> Empty` -- no `.*` -- is the legitimate way to write an
        unconditional rule and must keep working. """
        policy = _build(self._NO_SERVICES.replace('Empty.*', 'Empty'))

        self.assertEqual(policy.policies[('Client', 'Empty')].conditions, [])


class TestTheShippedExamples(unittest.TestCase):

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'fml-paper-policy.txt')),
        "examples/fml-paper-policy.txt not present")
    def test_fml_paper_policy_compiles_at_all(self):
        """ It did not. `All ---> All.ARP` raised `Service All.ARP unbekannt.`
        for a service `def role All` declares with `offers ARP` -- verified
        still failing at HEAD~8, so it predates this work. """
        with open(os.path.join(_HERE, 'examples', 'fml-paper-policy.txt'),
                  encoding='utf-8') as raw:
            policy = _build(raw.read())

        self.assertIn('protocol:arp', policy.roles_to_csv())

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'ifi-policy.txt')),
        "examples/ifi-policy.txt not present")
    def test_ifi_policy_is_under_specified_AND_SAYS_SO(self):
        """ A TRIPWIRE, not an endorsement -- see TODO item 19.

        `ifi-policy.txt` writes `Internet ---> Server.*` where `def role Server`
        is `vlan = 5` plus `includes Webserver` and declares no `offers`. Under
        the invariant that group offers nothing, so the rule cannot mean what
        its comment says ("Alle Rechner im Internet koennen die Server
        erreichen", HTTP and HTTPS per the rule above it).

        It used to compile -- to an UNCONDITIONAL cell, having also erased the
        RELATED,ESTABLISHED an earlier rule had set. Refusing is the
        improvement; correcting the inventory is an owner decision that has not
        been taken, so this pins the state rather than hiding it. When `Server`
        is given `offers HTTP` / `offers HTTPS` (or the rule names its services
        directly), this test goes red and should be replaced by one asserting
        the resulting cell.
        """
        with open(os.path.join(_HERE, 'examples', 'ifi-policy.txt'),
                  encoding='utf-8') as raw:
            text = raw.read()

        policy = Policy(strict=False)
        with self.assertRaises(NoServicesOfferedException) as caught:
            PolicyBuilder.build(text, policy)

        self.assertIn('Server', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
