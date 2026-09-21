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

""" `X ---> Y.*` emits its alternatives in DECLARATION order (TODO item 18).

It emitted them in `set` order. `add_reachability_policy`'s wildcard branch
collected the offered service NAMES into a `set` and iterated it, and set
iteration for strings follows a hash Python randomises per process -- so the
same inventory compiled to a different CSV from one run to the next:

    $ for i in 1 2 3 4; do policy_translator.py -c examples/ifi-policy.txt; done
    ... (protocol:tcp;port:80|protocol:tcp;port:443)
    ... (protocol:tcp;port:80|protocol:tcp;port:443)
    ... (protocol:tcp;port:443|protocol:tcp;port:80)
    ... (protocol:tcp;port:443|protocol:tcp;port:80)

Only `.*` reached that branch -- the named form builds a one-element list --
and no workload in the tree uses `.*`, so nothing measured was ever wrong.
It is fixed anyway because CLOUD_BENCH_PLAN.md §1.8 requires every artifact to
be recreatable from the raw data and the artifact-invariant tests (item 14)
compare matrices BYTE FOR BYTE; the wildcard is live in this project's thinking
(§1.9.4 measured `host2 <->> Internet.*`), and the first workload to use it
would have got an intermittently failing gate with no visible cause.

WHY DECLARATION ORDER rather than `sorted()`. Both are reproducible; only one
is the order the writer put on the page, which is what a reader comparing the
matrix against the inventory expects. `sorted()` would be a silent reordering
of the author's list for the convenience of the implementation. The tests below
therefore use an inventory whose declaration order is NOT alphabetical, so a
later "simplification" to `sorted()` turns them red rather than passing for the
wrong reason.

THE SYMPTOM IS INVISIBLE IN A SINGLE RUN, so `TestItIsReproducible` drives the
real CLI across several `PYTHONHASHSEED` values -- hash randomisation is fixed
at interpreter start, so it cannot be exercised in process. Measured on this
fixture before the fix: eight seeds produced eight DIFFERENT CSVs.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy
from policy_builder import PolicyBuilder


_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_HERE, 'policy_translator.py')

#: Declared Telnet, HTTPS, SSH, DNS, HTTP -- ports 23, 443, 22, 53, 80.
#: Alphabetically that is DNS, HTTP, HTTPS, SSH, Telnet -- ports 53, 80, 443,
#: 22, 23. The two orders share no position, which is the point: five services
#: also make the old `set` order differ between practically any two hash seeds.
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

def service DNS
    protocol = 'udp'
    port = 53
end

def service HTTP
    protocol = 'tcp'
    port = 80
end
"""

_DECLARED_PORTS = [23, 443, 22, 53, 80]
_ALPHABETICAL_PORTS = [53, 80, 443, 22, 23]

_INVENTORY = _SERVICES + """
def role Server
    description = 'the server'
    hosts = ['s1']
    offers Telnet
    offers HTTPS
    offers SSH
    offers DNS
    offers HTTP
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> Server.*
end
"""


def _build(text):
    policy = Policy(strict=True)
    PolicyBuilder.build(text, policy)
    return policy


def _ports(policy, role_from, role_to):
    return [c.get('port') for c in policy.policies[(role_from, role_to)].conditions]


class TestTheOrderIsTheOrderItWasWrittenIn(unittest.TestCase):

    def test_the_alternatives_follow_the_offers_lines(self):
        """ THE CHOICE. Not merely stable -- stable in the writer's order. """
        self.assertEqual(_ports(_build(_INVENTORY), 'Client', 'Server'),
                         _DECLARED_PORTS)

    def test_that_order_is_not_alphabetical(self):
        """ Guards the choice itself: `sorted()` is also reproducible, so
        without this the test above would pass on a silent reordering. """
        self.assertNotEqual(_DECLARED_PORTS, _ALPHABETICAL_PORTS)
        self.assertNotEqual(_ports(_build(_INVENTORY), 'Client', 'Server'),
                            _ALPHABETICAL_PORTS)

    def test_the_csv_spells_them_in_that_order(self):
        """ The CSV is what item 14 compares byte for byte, so assert the
        rendered text and not only the internal list. """
        row = [line for line in _build(_INVENTORY).roles_to_csv().splitlines()
               if line.startswith('Client,')]

        self.assertEqual(len(row), 1, row)
        self.assertIn(
            'protocol:tcp;port:23|protocol:tcp;port:443|protocol:tcp;port:22'
            '|protocol:udp;port:53|protocol:tcp;port:80', row[0])


class TestTheListNeverRepeatsAService(unittest.TestCase):
    """ The `set` deduplicated for free; an order-preserving replacement has to
    deduplicate WITHOUT moving the survivor, which is why the fix is
    `dict.fromkeys` and not a plain list comprehension.

    Two duplicates are reachable: a role naming a service twice, below, and one
    service offered by two subroles of a superrole, which lives in
    `test_superrole_services.py` because it only became reachable when item 19
    was fixed -- until then `X ---> Superrole.*` did not work at all, and
    dropping this deduplication turned no test red.
    """

    def test_a_role_offering_the_same_service_twice_emits_it_once(self):
        policy = _build(_SERVICES + """
def role Server
    description = 'the server'
    hosts = ['s1']
    offers Telnet
    offers HTTPS
    offers Telnet
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> Server.*
end
""")

        self.assertEqual(_ports(policy, 'Client', 'Server'), [23, 443])


class TestTheNamedFormIsUnaffected(unittest.TestCase):
    """ A control: only `.*` reached the `set`. If these moved, the change
    reached further than item 18 described. """

    def test_a_named_service_still_yields_exactly_itself(self):
        policy = _build(_SERVICES + """
def role Server
    description = 'the server'
    hosts = ['s1']
    offers Telnet
    offers HTTPS
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> Server.HTTPS
end
""")

        self.assertEqual(_ports(policy, 'Client', 'Server'), [443])

    def test_a_rule_with_no_service_yields_no_conditions(self):
        policy = _build(_SERVICES + """
def role Server
    description = 'the server'
    hosts = ['s1']
    offers Telnet
end

def role Client
    description = 'a client'
    hosts = ['c1']
end

def policies (default: deny)
    Client ---> Server
end
""")

        self.assertEqual(_ports(policy, 'Client', 'Server'), [])


class TestItIsReproducible(unittest.TestCase):
    """ THE PROPERTY ITEM 18 ASKED TO PIN. Hash randomisation is fixed when the
    interpreter starts, so this has to cross a process boundary. """

    _SEEDS = ('0', '1', '2', '3', '4', '5', '6', '7')

    def _csv(self, seed, inventory, directory):
        out = os.path.join(directory, 'out.%s.csv' % seed)
        done = subprocess.run(
            [sys.executable, _CLI, '-c', '-o', out, inventory],
            cwd=_HERE, env=dict(os.environ, PYTHONHASHSEED=seed),
            check=False, capture_output=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr.decode())
        with open(out, encoding='utf-8') as raw:
            return raw.read()

    def _assert_stable(self, text):
        with tempfile.TemporaryDirectory(prefix='wildcard_order_') as directory:
            inventory = os.path.join(directory, 'inventory.txt')
            with open(inventory, 'w', encoding='utf-8') as raw:
                raw.write(text)

            first = self._csv(self._SEEDS[0], inventory, directory)
            for seed in self._SEEDS[1:]:
                self.assertEqual(
                    self._csv(seed, inventory, directory), first,
                    "PYTHONHASHSEED=%s compiled the same policy differently" % seed)
            return first

    def test_every_hash_seed_compiles_the_same_csv(self):
        """ Eight seeds gave eight different answers before the fix. """
        self.assertIn('port:23|', self._assert_stable(_INVENTORY))

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'ifi-policy.txt')),
        "examples/ifi-policy.txt not present")
    def test_the_example_that_exposed_it_is_stable_too(self):
        """ The only file in the tree that uses `.*`, and the one the two
        spellings in this module's docstring came from. """
        with tempfile.TemporaryDirectory(prefix='wildcard_order_') as directory:
            example = os.path.join(_HERE, 'examples', 'ifi-policy.txt')
            first = self._csv(self._SEEDS[0], example, directory)
            for seed in self._SEEDS[1:]:
                self.assertEqual(self._csv(seed, example, directory), first, seed)

            # declaration order is `offers HTTP` then `offers HTTPS`
            self.assertIn('protocol:tcp;port:80|protocol:tcp;port:443', first)


if __name__ == '__main__':
    unittest.main()
