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

""" A block the inventory declares must be parsed or refused (TODO item 15).

`PolicyBuilder` finds role and service blocks with `regex.search` over the whole
file. A block that does not match is therefore SKIPPED -- and every block after
it is still found, so the result is not an error but a smaller inventory. The
policy then compiles against what survived and the run reports a clean verdict
for a matrix missing a row and a column.

That is how eight of wl_cloud's 25 roles disappeared: their description joined
two prefixes with ` + `, and `value_pattern` admits no `+`. The matrix came out
18x18 instead of 26x26, and the only reason it was noticed is that the emitter
knew how many roles it had written. A hand-written inventory has no such check.

`_assert_every_block_parsed` compares the blocks the file DECLARES against the
blocks the parser produced. The cause does not matter to it -- any block that
fails to parse for any reason is named and refused, which is what keeps the fix
from being a patch for one character.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy
from policy_builder import PolicyBuilder
from policy_exceptions import UnparsedBlockException


_SERVICE = (
    "def service SSH\n"
    "    protocol = 'tcp'\n"
    "    port = 22\n"
    "end\n"
)

_POLICY = (
    "def policies (default: deny)\n"
    "    Good ---> Good.SSH\n"
    "end\n"
)


def _role(name, description="plain", keyword="def"):
    return (
        "%s role %s\n"
        "    description = '%s'\n"
        "    hosts       = ['%s.example.com']\n"
        "    offers SSH\n"
        "end\n"
    ) % (keyword, name, description, name.lower())


def _build(inventory):
    policy = Policy(strict=True)
    PolicyBuilder.build(inventory + "\n" + _POLICY, policy)
    return policy


class TestEveryDeclaredBlockIsParsed(unittest.TestCase):

    def test_a_well_formed_inventory_still_builds(self):
        """ Without this the refusals below could pass for the wrong reason. """
        policy = _build(_SERVICE + "\n" + _role("Good") + "\n" + _role("Other"))
        self.assertIn('Good', policy.roles)
        self.assertIn('Other', policy.roles)
        self.assertIn('SSH', policy.services)

    def test_an_unparseable_role_is_refused_and_NAMED(self):
        """ The defect itself: a `+` in a value.

        Named, not merely refused -- "invalid syntax" over a 700-line inventory
        leaves the reader with the same search problem in a different shape.
        """
        inventory = (
            _SERVICE + "\n" + _role("Good") + "\n"
            + _role("Broken", description="two + parts"))

        with self.assertRaises(UnparsedBlockException) as caught:
            _build(inventory)

        self.assertIn('Broken', str(caught.exception))
        self.assertNotIn('Good', str(caught.exception))

    def test_a_block_AFTER_the_broken_one_is_not_what_saves_it(self):
        """ The property that made this silent: `search` finds later blocks.

        The broken block sits in the MIDDLE, so both neighbours parse and the
        inventory looks complete unless something counts.
        """
        inventory = (
            _SERVICE + "\n" + _role("First") + "\n"
            + _role("Broken", description="two + parts") + "\n"
            + _role("Last"))

        with self.assertRaises(UnparsedBlockException) as caught:
            _build(inventory)

        message = str(caught.exception)
        self.assertIn('Broken', message)
        self.assertNotIn('First', message)
        self.assertNotIn('Last', message)

    def test_an_unparseable_service_is_refused_too(self):
        broken = "def service BAD\n    protocol = 'tcp+udp'\n    port = 22\nend\n"

        with self.assertRaises(UnparsedBlockException) as caught:
            _build(_SERVICE + "\n" + broken + "\n" + _role("Good"))

        self.assertIn('BAD', str(caught.exception))

    def test_desc_is_refused_rather_than_ignored(self):
        """ `fpl_grammar.py` accepts `define`, `def`, `describe` AND `desc`;
        `PolicyBuilder.define_pattern` accepts only the first three. A `desc`
        block therefore used to vanish -- a divergence between two parsers of
        one language, which is the same failure wearing a different cause. """
        inventory = (
            _SERVICE + "\n" + _role("Good") + "\n"
            + _role("Terse", keyword="desc"))

        with self.assertRaises(UnparsedBlockException) as caught:
            _build(inventory)

        self.assertIn('Terse', str(caught.exception))

    def test_the_three_accepted_keywords_still_build(self):
        """ The other side of the line: refusing `desc` must not refuse the
        spellings the parser does take. wl_example writes `describe`, wl_up and
        wl_ifi write `def`. """
        for keyword in ('def', 'define', 'describe'):
            inventory = _SERVICE + "\n" + _role("Good", keyword=keyword)
            policy = _build(inventory)
            self.assertIn('Good', policy.roles, keyword)

    def test_a_commented_out_block_header_is_not_counted(self):
        """ `# def role Ghost` declares nothing, so demanding it be parsed would
        refuse a perfectly good inventory. """
        inventory = (
            _SERVICE + "\n"
            + "# def role Ghost\n"
            + "#     description = 'not real'\n"
            + "# end\n\n"
            + _role("Good"))

        policy = _build(inventory)
        self.assertIn('Good', policy.roles)
        self.assertNotIn('Ghost', policy.roles)


if __name__ == '__main__':
    unittest.main()
