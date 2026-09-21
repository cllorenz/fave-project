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

""" A direction that is stateful AND carries a service (TODO item 20).

`to_iptables` asked one question where there are two. `relatedrule` was

    {'state': 'RELATED,ESTABLISHED'} in conditions

and it gated `ip4rule`/`ip6rule`, so a direction carrying that condition emitted
no rule of its own. For a direction carrying ONLY that condition this is right:
the generator emits `-m conntrack --ctstate ESTABLISHED -j ACCEPT` once,
unconditionally, and that covers every such pair -- which is why suppressing
them is not a defect and why the tests below assert it still happens.

A direction can carry both, though:

    Watcher <->> Server          gives Server -> Watcher the return condition
    Server  ---> Watcher.HTTP    gives Server -> Watcher a service

and then the suppression threw the service away. The generated firewall
permitted LESS than the policy states, silently. Same conflation
`roles_to_csv` made when it printed such a pair as a bare `(X)`.

THE SECOND HALF, which the one-line reading misses. `singleway` decides whether
connection tracking can be switched off for a pair -- `--ctstate NEW,NOTRACK`
plus a raw/PREROUTING NOTRACK rule -- and it asks that of the REVERSE direction
only. That was sound while a stateful direction emitted nothing at all. Once a
mixed one emits rules, NOTRACK here would disable the very tracking the global
ESTABLISHED rule needs in order to admit this direction's return traffic, so
`singleway` now also requires that this direction is not itself stateful. The
first draft of this fix did not, and produced `--ctstate NEW,NOTRACK` on the
HTTP rule; that is what `test_no_NOTRACK...` pins.

NOTHING ELSE MOVES: every existing scenario -- the five in the checker, the
`wl_generic_fw` default scenario and `examples/ifi-policy.txt` -- generates a
byte-identical rule set, because none of them contains a mixed direction.
"""

import os
import sys
import unittest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(_TEST_DIR))
sys.path.append(_TEST_DIR)

from policy import Policy
from policy_builder import PolicyBuilder

# The block vocabulary lives with the block-wise tests, and reusing it keeps
# the two files from drifting apart about what a block is called.
from test_to_iptables import H_ACCESS, H_SUPPRESS, H_V4_STATE, parse_blocks


_ROLES = """
def service HTTP
    protocol = 'tcp'
    port = 80
end

def role Server
    description = 'the server'
    ipv4 = '10.0.1.0/24'
    offers HTTP
end

def role Watcher
    description = 'the watcher'
    ipv4 = '10.0.2.0/24'
    offers HTTP
end
"""

#: `Watcher <->> Server` puts the return condition on Server -> Watcher;
#: `Server ---> Watcher.HTTP` then gives that same direction a service.
_MIXED = _ROLES + """
def policies (default: deny)
    Watcher <->> Server
    Server ---> Watcher.HTTP
end
"""

#: The same inventory with only the stateful rule, so Server -> Watcher carries
#: the return condition and nothing else.
_STATE_ONLY = _ROLES + """
def policies (default: deny)
    Watcher <->> Server
end
"""

#: And with neither, so the pair is unconditional.
_PLAIN = _ROLES + """
def policies (default: deny)
    Watcher ---> Server
end
"""


def _rules(text):
    policy = Policy(strict=True)
    PolicyBuilder.build(text, policy)
    return {header: rules for header, rules in parse_blocks(policy.to_iptables())}


def _about(rules, source, target):
    return [r for r in rules if "-s %s" % source in r and "-d %s" % target in r]


_SERVER, _WATCHER = "10.0.1.0/24", "10.0.2.0/24"


class TestAMixedDirectionKeepsItsService(unittest.TestCase):

    def test_the_service_rule_is_emitted(self):
        """ THE DEFECT. It was suppressed entirely. """
        access = _about(_rules(_MIXED)[H_ACCESS], _SERVER, _WATCHER)

        self.assertEqual(len(access), 1, access)
        self.assertIn("--protocol tcp --dport 80", access[0])
        self.assertIn("-j ACCEPT", access[0])

    def test_the_service_is_matched_on_the_DESTINATION_port(self):
        """ The provider is the reached role, so traffic towards it is
        addressed to the service. A `--sport` here would permit the wrong
        direction of the connection. """
        access = _about(_rules(_MIXED)[H_ACCESS], _SERVER, _WATCHER)

        self.assertIn("--dport 80", access[0])
        self.assertNotIn("--sport", access[0])

    def test_the_forward_direction_is_untouched(self):
        """ `Watcher <->> Server` still yields its unconditional rule. """
        access = _about(_rules(_MIXED)[H_ACCESS], _WATCHER, _SERVER)

        self.assertEqual(len(access), 1, access)
        self.assertIn("--ctstate NEW", access[0])
        self.assertNotIn("--dport", access[0])


class TestAMixedDirectionKeepsItsTracking(unittest.TestCase):
    """ The half a one-line fix gets wrong. """

    def test_no_NOTRACK_on_the_service_rule(self):
        blocks = _rules(_MIXED)
        access = _about(blocks[H_ACCESS], _SERVER, _WATCHER)

        self.assertIn("--ctstate NEW", access[0])
        self.assertNotIn(
            "NOTRACK", access[0],
            "connection tracking was switched off for a direction whose other "
            "half is admitted by the global ESTABLISHED rule")

    def test_no_raw_PREROUTING_suppression_for_the_pair(self):
        blocks = _rules(_MIXED)

        self.assertEqual(
            _about(blocks.get(H_SUPPRESS, []), _SERVER, _WATCHER), [],
            "a raw/PREROUTING NOTRACK rule would bypass conntrack entirely")


class TestWhatMustNOTChange(unittest.TestCase):
    """ The suppression is correct for a direction that carries nothing but the
    stateful condition, and these keep it that way. """

    def test_a_state_only_direction_still_emits_no_rule_of_its_own(self):
        blocks = _rules(_STATE_ONLY)

        self.assertEqual(_about(blocks[H_ACCESS], _SERVER, _WATCHER), [])

    def test_because_the_global_ESTABLISHED_rule_covers_it(self):
        """ Without this the test above would be asserting a hole. """
        blocks = _rules(_STATE_ONLY)

        self.assertIn(
            "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT",
            blocks[H_V4_STATE])

    def test_an_unconditional_direction_still_emits_its_rule(self):
        """ The edge the narrowed predicate must not swallow: no conditions at
        all is not "covered by the ESTABLISHED rule", it is a plain permission.
        A predicate written as "has a non-stateful condition" would drop it. """
        access = _about(_rules(_PLAIN)[H_ACCESS], _WATCHER, _SERVER)

        self.assertEqual(len(access), 1, access)
        self.assertIn("-j ACCEPT", access[0])


class TestTheGenericBenchmarkScenarioIsUnchanged(unittest.TestCase):
    """ `bench/wl_generic_fw` checks a firewall rule set against an FPL policy,
    and its default scenario is what gave this mechanism its confidence. It has
    three state-only directions and no mixed one, so it must not move. """

    _SCENARIO = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        'fave', 'bench', 'wl_generic_fw', 'default')

    @unittest.skipUnless(os.path.isdir(_SCENARIO), "wl_generic_fw not present")
    def test_it_has_no_mixed_direction_and_so_cannot_catch_this(self):
        """ Stated as a test because it is the reason the defect survived: the
        scenario cannot exercise it. If a mixed direction is ever added here,
        this goes red and should be replaced by an assertion about its rules. """
        from policy import RELATED_CONDITION

        policy = Policy(strict=False)
        with open(os.path.join(self._SCENARIO, 'inventory.txt')) as raw:
            inventory = raw.read()
        with open(os.path.join(self._SCENARIO, 'policy.txt')) as raw:
            rules = raw.read()
        PolicyBuilder.build(inventory + "\n" + rules, policy)

        mixed = [
            key for key, pol in policy.policies.items()
            if RELATED_CONDITION in getattr(pol, 'conditions', [])
            and len(pol.conditions) > 1]

        self.assertEqual(mixed, [])


if __name__ == '__main__':
    unittest.main()
