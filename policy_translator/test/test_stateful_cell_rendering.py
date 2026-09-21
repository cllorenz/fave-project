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

""" A stateful cell keeps its services in the matrix (TODO item 19).

`roles_to_csv` short-circuited: if `{'state': 'RELATED,ESTABLISHED'}` was among
a pair's conditions the cell was printed `(X)` and every other condition was
dropped. `examples/ifi-policy.txt` showed it -- `Internet` -> `Webserver`
printed `(X)` while the policy held ports 80 and 443.

NOT COSMETIC. `bench/reach_csv_to_checks.py` reads `(X)` as "related traffic and
NOTHING else" and emits a must-NOT-reach check for everything unrelated:

    ! s=source.c1 && EF p=probe.s1 && f=related:0

For a pair that also permits HTTP that check is the OPPOSITE of the policy, so
the rendering did not merely hide information, it inverted a verification
claim.

The fix is one rendering path with `X` as the operand the stateful condition
renders as, so a cell whose ONLY condition is that one still prints exactly
`(X)` -- by construction rather than by a second branch, which is why the 738
such cells in the tree are untouched.

WHY `X` AND NOT `state:RELATED,ESTABLISHED`: the value contains a comma and the
cell is comma-separated, so writing it would split the row. That is also why
`-/->>`, whose condition is `state = NEW,INVALID`, is refused rather than
written -- it used to produce `(state:NEW` and `INVALID)` in adjacent columns,
silently.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy, RELATED_CONDITION
from policy_builder import PolicyBuilder
from policy_exceptions import UnrenderableConditionException


_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SERVICES = """
def service HTTP
    protocol = 'tcp'
    port = 80
end

def service HTTPS
    protocol = 'tcp'
    port = 443
end
"""

_ROLES = _SERVICES + """
def role Server
    description = 'the server'
    hosts = ['s1']
    offers HTTP
    offers HTTPS
end

def role Client
    description = 'a client'
    hosts = ['c1']
end
"""


def _build(text, strict=True):
    policy = Policy(strict=strict)
    PolicyBuilder.build(text, policy)
    return policy


def _cell(policy, role_from, role_to):
    rows = {line.split(',')[0]: line
            for line in policy.roles_to_csv().splitlines()[1:]}
    header = policy.roles_to_csv().splitlines()[0].split(',')
    return rows[role_from].split(',')[header.index(role_to)]


def _operands(cell):
    """ The alternatives of a conditional cell, without its parentheses. """
    return cell.lstrip('(').rstrip(')').split('|')


class TestAStateOnlyCellIsUnchanged(unittest.TestCase):
    """ 738 cells in the tree are this shape. They must render byte for byte
    as before, or the fix would move every stateful workload's matrix. """

    def test_a_stateful_return_direction_still_prints_X(self):
        policy = _build(_ROLES + """
def policies (default: deny)
    Client <->> Server
end
""")

        self.assertEqual(_cell(policy, 'Server', 'Client'), '(X)')
        self.assertEqual(
            policy.policies[('Server', 'Client')].conditions,
            [RELATED_CONDITION],
            "the fixture stopped being the state-only shape")


class TestAMixedCellKeepsItsServices(unittest.TestCase):

    def test_the_services_appear_beside_the_X(self):
        """ THE DEFECT. `Client <->> Server` gives Server->Client the stateful
        condition; `Server ---> Client.HTTP` then adds a service to the same
        pair, and the cell used to print `(X)` alone. """
        policy = _build(_ROLES + """
def role Watcher
    description = 'watches'
    hosts = ['w1']
    offers HTTP
end

def policies (default: deny)
    Watcher <->> Server
    Server ---> Watcher.HTTP
end
""")

        cell = _cell(policy, 'Server', 'Watcher')

        self.assertIn('X', _operands(cell))
        self.assertIn('protocol:tcp;port:80', _operands(cell))

    def test_the_operands_follow_condition_order(self):
        """ Deliberately not "X first": the operand order is the order the
        conditions were established, the same choice item 18 made for `.*`.
        Imposing a position would reorder the author's rules for the
        convenience of the renderer. """
        policy = _build(_ROLES + """
def role Watcher
    description = 'watches'
    hosts = ['w1']
    offers HTTP
end

def policies (default: deny)
    Watcher <->> Server
    Server ---> Watcher.HTTP
end
""")

        conditions = policy.policies[('Server', 'Watcher')].conditions
        operands = _operands(_cell(policy, 'Server', 'Watcher'))

        self.assertEqual(
            operands.index('X'), conditions.index(RELATED_CONDITION))


class TestTheCommaThatCannotBeWritten(unittest.TestCase):
    """ A cell is comma-separated, so a value containing a comma splits the row
    and the file ends up with more fields than the header has columns. """

    def test_a_NEW_INVALID_condition_is_refused_not_written(self):
        """ `-/->>` produced `(state:NEW` and `INVALID)` in adjacent columns,
        with no error. No inventory in the tree writes it, so this refuses a
        shape that is reachable rather than one that is used. """
        policy = _build("""
def role A
    description = 'a'
    hosts = ['a1']
end

def role B
    description = 'b'
    hosts = ['b1']
end

def policies (default: allow)
    A -/->> B
end
""", strict=False)

        with self.assertRaises(UnrenderableConditionException) as caught:
            policy.roles_to_csv()

        self.assertIn('NEW,INVALID', str(caught.exception))

    def test_the_related_condition_is_the_one_comma_that_is_spelled(self):
        """ At the helper, because the cell tests above would pass on a
        rendering that merely happened to avoid the comma. """
        policy = _build(_ROLES + """
def policies (default: deny)
    Client <->> Server
end
""")

        self.assertEqual(
            policy._condition_to_csv(RELATED_CONDITION, 'Server'), 'X')


class TestTheShippedExample(unittest.TestCase):

    @unittest.skipUnless(
        os.path.isfile(os.path.join(_HERE, 'examples', 'ifi-policy.txt')),
        "examples/ifi-policy.txt not present")
    def test_ifi_policy_shows_the_webservers_ports_in_the_matrix(self):
        """ The cell the defect was found in. """
        with open(os.path.join(_HERE, 'examples', 'ifi-policy.txt'),
                  encoding='utf-8') as raw:
            policy = _build(raw.read(), strict=False)

        operands = _operands(_cell(policy, 'Internet', 'Webserver'))

        self.assertIn('X', operands)
        self.assertIn('protocol:tcp;port:80', operands)
        self.assertIn('protocol:tcp;port:443', operands)


if __name__ == '__main__':
    unittest.main()
