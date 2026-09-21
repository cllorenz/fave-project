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

""" A comment may appear inside a role or service block (TODO item 15).

It could not. `role_content` was EITHER a run of attribute/`includes`/`offers`
lines OR a run of comments, never interleaved, so annotating a single role
dropped the whole block. `policies_regex` has always allowed interleaved
comments and `wl_ifi/reach_stateless.txt` uses them, so a writer met the
inconsistency the first time they tried to explain a role.

TWO HALVES, AND THE SECOND IS THE ONE THAT BITES. The block patterns decide
whether a role parses; `role_attr_regex`, `role_incl_regex` and
`role_offers_regex` decide what is read OUT of it, and they run over the same
text. Teaching only the block patterns about comments turns a loud refusal into
a SILENT LOSS -- measured while making the change: `description = 'x'  # note`
left a role with no description, and an annotated `offers` left a role offering
nothing, surfacing only as "Service unknown" from the policy much later. So
every test here that admits a comment also asserts the annotated line was still
read.

`#` is deliberately NOT added to `value_pattern`. Folding it in appears to work
-- it passes every behavioural test here -- but only because
`Role.add_attribute` hands the captured group to `ast.literal_eval`, which
treats the trailing text as a PYTHON comment and drops it. That is a coincidence
between two languages rather than a property of this one, and it would stop
holding the moment a consumer read the group as text, so
`TestTheValueGroupHoldsOnlyTheValue` pins the group's content directly.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import Policy
from policy_builder import PolicyBuilder


_SERVICE = "def service SSH\n    protocol = 'tcp'\n    port = 22\nend\n"
_POLICY = "def policies (default: deny)\n    Plain ---> Plain.SSH\nend\n"


def _build(inventory):
    policy = Policy(strict=True)
    PolicyBuilder.build(inventory + "\n" + _POLICY, policy)
    return policy


def _plain(body):
    return "def role Plain\n%send\n" % body


class TestCommentsInsideABlock(unittest.TestCase):

    def test_a_comment_on_its_own_line_inside_a_role(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    # what this role is for\n"
            "    description = 'the office'\n"
            "    hosts       = ['h1']\n"
            "    offers SSH\n"))

        self.assertIn('Plain', policy.roles)
        self.assertEqual(
            policy.roles['Plain'].attributes['description'], 'the office')

    def test_a_comment_between_two_attributes(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    description = 'the office'\n"
            "    # the subnet it stands for\n"
            "    ipv4        = '10.0.0.0/24'\n"
            "    offers SSH\n"))

        self.assertEqual(
            policy.roles['Plain'].attributes['ipv4'], '10.0.0.0/24')

    def test_a_comment_as_the_last_line_before_end(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    description = 'the office'\n"
            "    offers SSH\n"
            "    # nothing follows\n"))

        self.assertIn('Plain', policy.roles)

    def test_a_comment_inside_a_SERVICE_block(self):
        policy = _build(
            "def service SSH\n"
            "    # the remote shell\n"
            "    protocol = 'tcp'\n"
            "    port = 22\n"
            "end\n\n"
            + _plain("    description = 'd'\n    offers SSH\n"))

        self.assertIn('SSH', policy.services)
        self.assertEqual(policy.services['SSH'].attributes['port'], 22)


class TestTrailingCommentsAreNotLossy(unittest.TestCase):
    """ Every one of these asserts the annotated line was still READ. A test
    that only checked the block parses would pass on the silent-loss bug. """

    def test_an_attribute_keeps_its_value(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    description = 'the office'  # why it exists\n"
            "    ipv4        = '10.0.0.0/24' # the subnet\n"
            "    offers SSH\n"))

        attributes = policy.roles['Plain'].attributes
        self.assertEqual(attributes['description'], 'the office')
        self.assertEqual(attributes['ipv4'], '10.0.0.0/24')

    def test_the_comment_does_not_leak_into_the_value(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    description = 'the office'  # why it exists\n"
            "    offers SSH\n"))

        self.assertNotIn(
            '#', str(policy.roles['Plain'].attributes['description']),
            "the comment was read as part of the value")

    def test_an_offers_line_still_offers(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    description = 'd'\n"
            "    offers SSH  # the only one\n"))

        offered = policy.roles['Plain'].get_services()
        self.assertTrue(
            any('SSH' in services for services in offered.values()),
            "an annotated `offers` line was dropped: %s" % offered)

    def test_an_includes_line_still_includes(self):
        policy = _build(
            _SERVICE + "\n"
            + _plain("    description = 'd'\n    offers SSH\n") + "\n"
            + "def role Group\n"
              "    includes Plain  # the only member\n"
              "end\n")

        self.assertEqual(policy.roles['Group'].get_roles(), ['Plain'])

    def test_a_service_attribute_keeps_its_value(self):
        policy = _build(
            "def service SSH\n"
            "    protocol = 'tcp'  # not udp\n"
            "    port = 22         # the well-known one\n"
            "end\n\n"
            + _plain("    description = 'd'\n    offers SSH\n"))

        self.assertEqual(policy.services['SSH'].attributes['protocol'], 'tcp')
        self.assertEqual(policy.services['SSH'].attributes['port'], 22)

    def test_a_tab_indented_comment_is_accepted_too(self):
        """ The grammar admits a tab or four spaces as the indent, so the
        comment forms must not quietly require one of them. """
        policy = _build(_SERVICE + "\n" + _plain(
            "\tdescription = 'd'\t# tab before the comment\n"
            "\toffers SSH\n"))

        self.assertEqual(policy.roles['Plain'].attributes['description'], 'd')


class TestTheValueGroupHoldsOnlyTheValue(unittest.TestCase):
    """ At the REGEX level, because every behavioural assertion above survives
    the comment leaking into the value -- `ast.literal_eval` drops it. """

    def test_the_captured_value_excludes_a_trailing_comment(self):
        match = PolicyBuilder.role_attr_regex.search(
            "    description = 'the office'  # why it exists\n")

        self.assertIsNotNone(match)
        self.assertNotIn(
            '#', match.group('value'),
            "the comment was captured as part of the value; it only looks "
            "harmless because ast.literal_eval treats it as a Python comment")
        self.assertEqual(match.group('value').strip(), "'the office'")

    def test_the_captured_value_is_unchanged_without_a_comment(self):
        match = PolicyBuilder.role_attr_regex.search(
            "    description = 'the office'\n")

        self.assertIsNotNone(match)
        self.assertEqual(match.group('value').strip(), "'the office'")


class TestWhatWasAlreadyAllowedStillIs(unittest.TestCase):
    """ Comments BETWEEN blocks, and blank lines inside them, worked before.
    A grammar change that silently traded one for the other would look like a
    fix in the tests above. """

    def test_a_comment_before_a_block(self):
        policy = _build(
            "# the remote shell\n" + _SERVICE + "\n"
            + "# and who may use it\n"
            + _plain("    description = 'd'\n    offers SSH\n"))

        self.assertIn('SSH', policy.services)
        self.assertIn('Plain', policy.roles)

    def test_a_blank_line_inside_a_block(self):
        policy = _build(_SERVICE + "\n" + _plain(
            "    description = 'd'\n"
            "\n"
            "    offers SSH\n"))

        self.assertIn('Plain', policy.roles)

    def test_a_block_with_no_body_at_all(self):
        """ Built with its own policy: the shared one names `Plain.SSH`, and a
        role with no body offers nothing, so reusing it would fail in the
        POLICY rather than tell us anything about the block. """
        policy = Policy(strict=True)
        PolicyBuilder.build(
            _SERVICE + "\ndef role Plain\nend\n\n"
            "def policies (default: deny)\n    Plain ---> Plain\nend\n",
            policy)

        self.assertIn('Plain', policy.roles)


if __name__ == '__main__':
    unittest.main()
