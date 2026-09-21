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

    All ---> All.ARP        ServiceUnknownException: Service All.ARP is unknown.

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
    def test_fml_paper_policy_gets_PAST_the_superrole_and_fails_on_its_data(self):
        """ This file used to raise `Service All.ARP is unknown.` -- the superrole
        defect this module is about -- and it now gets past that and is refused
        for a different, real reason: `protocol = 'arp'` is not an IP protocol
        (TODO item 21). Asserting WHICH refusal is the point; a test that only
        checked "raises" would have passed before the superrole fix too.

        Item 19's property itself is asserted on fixtures above
        (`test_a_service_named_on_the_group_resolves`), so nothing is lost by
        this file no longer compiling end to end.
        """
        from policy_exceptions import UnknownProtocolException

        with open(os.path.join(_HERE, 'examples', 'fml-paper-policy.txt'),
                  encoding='utf-8') as raw:
            text = raw.read()

        with self.assertRaises(UnknownProtocolException) as caught:
            _build(text)

        self.assertIn('arp', str(caught.exception))
        self.assertNotIn('is unknown', str(caught.exception),
                         "still failing on the superrole, not on the protocol")

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'ifi-policy.txt')),
        "examples/ifi-policy.txt not present")
    def test_ifi_policy_reaches_the_webserver_with_HTTP_and_HTTPS(self):
        """ The cell this whole item was visible in.

        The file used to write `Internet ---> Server.*` over a `def role Server`
        that is `vlan = 5` plus `includes Webserver` and declares no `offers`.
        Under the invariant that group offers nothing, so the rule could not
        mean what its own comment says -- and before the refusal it compiled to
        an UNCONDITIONAL cell that had also erased the `RELATED,ESTABLISHED` an
        earlier rule set for the pair. Both wildcard rules now name the
        webserver and its two services directly (owner, 2026-09-21), which is
        what the comment described all along.

        Note `roles_to_csv` still prints this cell as `(X)`: the renderer
        short-circuits whenever `RELATED,ESTABLISHED` is among the conditions,
        so the ports are in the policy but not in the matrix. That is a
        rendering question, not a policy one, which is why this asserts the
        conditions.
        """
        with open(os.path.join(_HERE, 'examples', 'ifi-policy.txt'),
                  encoding='utf-8') as raw:
            text = raw.read()

        self.assertNotIn('.*', text, "the wildcard rules were meant to go")

        policy = Policy(strict=False)
        PolicyBuilder.build(text, policy)
        conditions = policy.policies[('Internet', 'Webserver')].conditions

        self.assertEqual(sorted(c['port'] for c in conditions if 'port' in c),
                         [80, 443])
        self.assertIn({'state': 'RELATED,ESTABLISHED'}, conditions,
                      "the earlier rule's condition was erased")


if __name__ == '__main__':
    unittest.main()
