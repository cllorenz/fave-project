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

""" A superrole offers services, in all three spellings (TODO item 19).

It offered none, in any of them. `Superrole.offers_service` was `return False`
unconditionally -- "only roles offer services" -- while the same class describes
itself as containing "all services of a role or only a certain subset of
services", `add_service` propagates to every subrole and records `subservices`,
and `add_reachability_policy`'s docstring promises that "if the reached role is
a superrole, all subservices will be considered". The guard believed the method:

    includes Alpha          `Both.*` yielded NO conditions at all
    includes Alpha.*        ServiceUnknownException: Service Both.Telnet unbekannt.
    includes Alpha.HTTPS    ServiceUnknownException: Service Both.HTTPS unbekannt.

THE FIRST ROW IS THE DANGEROUS ONE, and not for the obvious reason. An empty
condition list is how FPL spells an UNCONDITIONAL rule, and
`ReachabilityPolicy.update_conditions` states that "the empty list overpowers
all other lists of conditions" -- so a `.*` resolving to nothing did not merely
fail to restrict its own rule, it ERASED the conditions an earlier rule had
established for the same pair. That is visible in a file this repository ships:
`examples/ifi-policy.txt` writes `Internet ---> Server.*` for a webserver
offering HTTP and HTTPS, and the matrix cell came out plain `X`.

The two exceptions were wrong but loud. `examples/fml-paper-policy.txt` -- the
FML paper's own policy -- writes `All ---> All.ARP` over a superrole with
`offers ARP` and could not be compiled at all. It compiles here, which is what
closes the item.

WHAT A SUPERROLE OFFERS (owner decision 2026-09-21): the services of its
subroles, narrowed where the inventory narrowed them. `subservices` records the
narrowing, so an EMPTY entry means nothing was narrowed rather than nothing is
offered -- reading it as the latter is the whole defect.
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


class TestTheThreeSpellings(unittest.TestCase):
    """ One test per row of the table in this module's docstring. """

    def test_an_unnarrowed_include_offers_the_members_services(self):
        """ Was: no conditions at all, i.e. UNCONDITIONAL reachability. """
        policy = _build(_group("    includes Alpha\n    includes Beta\n"))

        # Telnet, HTTPS from Alpha; HTTPS again from Beta, then SSH.
        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [23, 443, 22])

    def test_an_explicit_wildcard_include_says_the_same_thing(self):
        """ Was: ServiceUnknownException naming the superrole. `includes
        Alpha.*` is the long form of `includes Alpha` and must not differ. """
        policy = _build(_group("    includes Alpha.*\n    includes Beta.*\n"))

        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [23, 443, 22])

    def test_a_named_include_narrows_and_that_narrowing_survives(self):
        """ Was: ServiceUnknownException. The reason the empty entry cannot
        simply be replaced by the subrole's services everywhere -- `includes
        Alpha.HTTPS` is a deliberate restriction. """
        policy = _build(_group("    includes Alpha.HTTPS\n    includes Beta.SSH\n"))

        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [443, 22])

    def test_a_service_named_on_the_superrole_resolves(self):
        """ `X ---> Superrole.SERVICE`, the form fml-paper-policy.txt uses. """
        policy = _build(_group("    includes Alpha\n", rule='Client ---> Both.Telnet'))

        self.assertEqual(_ports(policy, 'Client', 'Alpha'), [23])

    def test_a_service_no_member_offers_is_still_refused(self):
        """ The other side of the line: making superroles offer services must
        not make them offer ANY service. """
        with self.assertRaises(ServiceUnknownException):
            _build(_group("    includes Alpha\n", rule='Client ---> Both.SSH'))


class TestAnEmptyWildcardIsRefused(unittest.TestCase):
    """ The second half of the fix, and the one that outlives it: a `.*` over a
    role offering nothing compiled to an unconditional rule. """

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

    def test_a_wildcard_over_a_superrole_whose_members_offer_nothing(self):
        with self.assertRaises(NoServicesOfferedException) as caught:
            _build("""
def role Empty
    description = 'offers nothing'
    hosts = ['e1']
end

def role Group
    includes Empty
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> Group.*
end
""")

        self.assertIn('Group', str(caught.exception))

    def test_the_refusal_does_not_reach_a_rule_naming_no_service(self):
        """ `Client ---> Empty` -- no `.*` -- is the legitimate way to write an
        unconditional rule and must keep working. """
        policy = _build(self._NO_SERVICES.replace('Empty.*', 'Empty'))

        self.assertEqual(policy.policies[('Client', 'Empty')].conditions, [])


class TestTheShippedExamplesCompile(unittest.TestCase):
    """ Both examples are policies someone published, not fixtures, which is
    why they are the proof rather than a nicety. """

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'fml-paper-policy.txt')),
        "examples/fml-paper-policy.txt not present")
    def test_fml_paper_policy_compiles_at_all(self):
        """ It did not. `All ---> All.ARP` raised `Service All.ARP unbekannt.`
        -- verified still failing at HEAD~8, so it predates this work. """
        with open(os.path.join(_HERE, 'examples', 'fml-paper-policy.txt'),
                  encoding='utf-8') as raw:
            policy = _build(raw.read())

        self.assertIn('protocol:arp', policy.roles_to_csv())

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'ifi-policy.txt')),
        "examples/ifi-policy.txt not present")
    def test_the_internet_no_longer_reaches_the_webserver_unconditionally(self):
        """ THE SILENT WIDENING, in a tracked file. `Internet ---> Server.*`
        resolved to nothing, and the empty list then erased the conditions the
        earlier `MitInternetzugriff <->> Internet` rule had set for the pair. """
        with open(os.path.join(_HERE, 'examples', 'ifi-policy.txt'),
                  encoding='utf-8') as raw:
            policy = Policy(strict=False)
            PolicyBuilder.build(raw.read(), policy)

        conditions = policy.policies[('Internet', 'Webserver')].conditions

        self.assertNotEqual(
            conditions, [],
            "an empty condition list is an UNCONDITIONAL rule, which is wider "
            "than the HTTP and HTTPS the inventory asks for")
        self.assertEqual(sorted(c['port'] for c in conditions if 'port' in c),
                         [80, 443])
        self.assertIn({'state': 'RELATED,ESTABLISHED'}, conditions,
                      "the earlier rule's condition was erased")


if __name__ == '__main__':
    unittest.main()
