#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2019 Claas Lorenz

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

""" This module provides unit tests for the PolicyBuilder class.
"""

import os
import subprocess
import sys
import unittest

from policy import Policy
from policy_builder import PolicyBuilder
from policy_exceptions import (
    NameTakenException, InvalidValueException, InvalidSyntaxException,
    RoleUnknownException,
)

class TestPolicyBuilder(unittest.TestCase):

    """ This class provides unit tests for the PolicyBuilder class.
    """

    def setUp(self):
        self.service_str = '\n'.join([
            "# Service HTTP without TLS",
            "describe service HTTP",
            "\tport = 80",
            "\tprotocol = 'tcp'",
            "end"
        ])

        self.role_str = '\n'.join([
            "# Represents all webservers",
            "def role WebService",
            "\thosts = 'http1.foo.bar','http2.foo.bar'",
            "\tvlan = 23",
            "\toffers HTTP",
            "end"
        ])

        self.policy_str = '\n'.join([
            "define policies (default: deny)",
            "# Only allow communication to the webservices via HTTP",
            "\tInternet <->> WebService.HTTP",
            "end"
        ])

        self.policy = Policy()
        self.expectation = Policy()


    def tearDown(self):
        del self.policy
        del self.expectation


    def test_build_roles_and_services(self):

        """ Tests building roles and services from their respective string
            representation.
        """

        PolicyBuilder.build_roles_and_services(
            "%s\n%s\n" % (self.service_str, self.role_str), self.policy
        )

        self.expectation.add_role("WebService")
        self.expectation.add_service("HTTP")

        self.expectation.services["HTTP"].add_attribute("port", "80")
        self.expectation.services["HTTP"].add_attribute("protocol", "\"tcp\"")

        self.expectation.roles["WebService"].add_attribute(
            "hosts", "\"http1.foo.bar\",\"http2.foo.bar\""
        )
        self.expectation.roles["WebService"].add_attribute("vlan", "23")
        self.expectation.roles["WebService"].add_service("HTTP")

        self.assertEqual(self.policy, self.expectation)


    def test_build_policies(self):

        """ Tests building policies from its string representation.
        """

        self.test_build_roles_and_services()

        PolicyBuilder.build_policies(self.policy_str + '\n', self.policy)

        # 'Internet <->> WebService.HTTP' under default-deny expands to (see
        # PolicyBuilder.build_policies): a forward policy carrying the HTTP
        # service, a *reverse* RELATED,ESTABLISHED policy for the return path,
        # and -- in non-strict mode -- an implicit self-reachability policy per
        # atomic role. (The previous expectation put the state condition on the
        # forward direction and omitted self-reachability; it only passed
        # because Policy.__eq__ did not compare the policies dict.)
        self.expectation.add_reachability_policy(
            "Internet", "WebService", service_to="HTTP"
        )
        self.expectation.add_reachability_policy(
            "WebService", "Internet", condition={"state": "RELATED,ESTABLISHED"}
        )
        self.expectation.add_reachability_policy("WebService", "WebService")
        self.expectation.add_reachability_policy("Internet", "Internet")

        self.assertEqual(self.policy, self.expectation)

    def test_build(self):

        """ Test building roles, services, and policies from their string
            representations.
        """

        self.test_build_policies()

        policy = Policy()
        PolicyBuilder.build(
            "%s\n%s\n%s\n" % (self.role_str, self.service_str, self.policy_str),
            policy
        )

        self.assertEqual(policy, self.expectation)


class TestPolicyOperators(unittest.TestCase):
    """ Tests the reachability semantics of each FPL operator.

    Uses strict mode so the implicit self-reachability policies are suppressed,
    leaving only the operator's own effect on the policies dict. Conditions are
    asserted directly (not via Policy equality).
    """

    def _build(self, default, operator_line):
        policy = Policy(strict=True)
        policy.add_role('A')
        policy.add_role('B')
        PolicyBuilder.build_policies(
            'define policies (default: %s)\n\t%s\nend\n' % (default, operator_line),
            policy
        )
        return {key: value.conditions for key, value in policy.policies.items()}

    # --- default-deny operators ---------------------------------------------

    def test_stateful_bidirectional_deny(self):
        """ '<->>': forward (unconditional) + reverse RELATED,ESTABLISHED. """
        self.assertEqual(self._build('deny', 'A <->> B'), {
            ('A', 'B'): [],
            ('B', 'A'): [{'state': 'RELATED,ESTABLISHED'}],
        })

    def test_unidirectional_deny(self):
        """ '--->': a single forward policy. """
        self.assertEqual(self._build('deny', 'A ---> B'), {('A', 'B'): []})

    def test_bidirectional_deny(self):
        """ '<-->': forward and reverse, both unconditional. """
        self.assertEqual(self._build('deny', 'A <--> B'), {
            ('A', 'B'): [],
            ('B', 'A'): [],
        })

    def test_deny_only_operators_ignored_under_allow(self):
        """ A deny-default operator is silently ignored under default allow. """
        self.assertEqual(self._build('allow', 'A ---> B'), {})

    # --- default-allow operators ---------------------------------------------

    def test_unidirectional_forbid(self):
        """ '--/->': a single forbidden (forward) policy. """
        self.assertEqual(self._build('allow', 'A --/-> B'), {('A', 'B'): []})

    def test_bidirectional_forbid(self):
        """ '<-/->': forbidden forward and reverse. """
        self.assertEqual(self._build('allow', 'A <-/-> B'), {
            ('A', 'B'): [],
            ('B', 'A'): [],
        })

    def test_stateful_forbid(self):
        """ '-/->>': conditionally forbidden NEW,INVALID. """
        self.assertEqual(self._build('allow', 'A -/->> B'), {
            ('A', 'B'): [{'state': 'NEW,INVALID'}],
        })

    def test_allow_only_operator_ignored_under_deny(self):
        """ An allow-default operator is silently ignored under default deny. """
        self.assertEqual(self._build('deny', 'A --/-> B'), {})

    def test_self_reachability_added_in_non_strict_mode(self):
        """ Non-strict mode adds an implicit role->role policy per atomic role. """
        policy = Policy(strict=False, use_internet=False)
        policy.add_role('A')
        policy.add_role('B')
        PolicyBuilder.build_policies(
            'define policies (default: deny)\n\tA ---> B\nend\n', policy
        )
        self.assertIn(('A', 'A'), policy.policies)
        self.assertIn(('B', 'B'), policy.policies)


class TestPolicyBuilderErrors(unittest.TestCase):
    """ Tests the FPL error/exception paths (previously untested). """

    def test_duplicate_role_raises(self):
        policy = Policy()
        policy.add_role('A')
        with self.assertRaises(NameTakenException):
            policy.add_role('A')

    def test_invalid_attribute_value_raises(self):
        policy = Policy()
        policy.add_role('A')
        with self.assertRaises(InvalidValueException):
            policy.roles['A'].add_attribute('vlan', 'not-a-number')

    def test_malformed_roles_block_raises(self):
        policy = Policy()
        with self.assertRaises(InvalidSyntaxException):
            PolicyBuilder.build_roles_and_services('this is not valid fpl\n', policy)

    def test_policy_referencing_unknown_role_raises(self):
        policy = Policy(strict=True)
        policy.add_role('A')
        with self.assertRaises(RoleUnknownException):
            PolicyBuilder.build_policies(
                'define policies (default: deny)\n\tA ---> Nonexistent\nend\n',
                policy
            )


if __name__ == '__main__':
    unittest.main()


class TestSuperroleSelfExpansion(unittest.TestCase):

    """ Tests that superrole expansion does not fabricate self-reachability.

    Strict mode's contract is that a role reaches itself only when an FPL rule
    says so. Expanding a superrole over its own members used to break that
    silently: every member of `Grp <--> Grp` picked up a diagonal although no
    rule named a member reaching itself. Non-strict mode is unaffected -- it
    grants every atomic role a diagonal by design.
    """

    def _policy(self, strict):
        policy = Policy(strict=strict, use_internet=False)
        policy.add_role('A')
        policy.add_role('B')
        policy.add_superrole('Grp')
        policy.roles['Grp'].add_subrole('A')
        policy.roles['Grp'].add_subrole('B')
        return policy

    def _build(self, policy, rule):
        PolicyBuilder.build_policies(
            'define policies (default: deny)\n\t%s\nend\n' % rule, policy
        )
        return policy.policies

    def test_superrole_self_rule_grants_no_member_diagonal(self):
        """ `Grp <--> Grp` connects the members without self-reachability. """
        policies = self._build(self._policy(strict=True), 'Grp <--> Grp')
        self.assertIn(('A', 'B'), policies)
        self.assertIn(('B', 'A'), policies)
        self.assertNotIn(('A', 'A'), policies)
        self.assertNotIn(('B', 'B'), policies)

    def test_member_to_own_superrole_grants_no_diagonal(self):
        """ A member reaching its own superrole does not reach itself. """
        policies = self._build(self._policy(strict=True), 'A <--> Grp')
        self.assertIn(('A', 'B'), policies)
        self.assertNotIn(('A', 'A'), policies)

    def test_explicit_atomic_self_rule_survives(self):
        """ A diagonal written between two atomic roles is kept (wl_up's Wifi). """
        policies = self._build(self._policy(strict=True), 'A <--> A')
        self.assertIn(('A', 'A'), policies)

    def test_non_strict_mode_still_grants_every_diagonal(self):
        """ The guard is strict-mode only; loose mode keeps its own semantics. """
        policies = self._build(self._policy(strict=False), 'Grp <--> Grp')
        self.assertIn(('A', 'A'), policies)
        self.assertIn(('B', 'B'), policies)

class _Deadline(unittest.TestCase):

    r""" Base for the two catastrophic-backtracking guards.

    THE PARSE RUNS IN A SUBPROCESS, and that is the whole design. A budget
    checked after the fact -- `t = time.time(); parse(); assertLess(...)` --
    cannot fail when the defect is present: the shipped patterns take longer
    than any run will wait, so the test HANGS instead of reporting. Worse, the
    obvious in-process rescue does not work either, because a signal handler
    only runs between bytecode instructions and `re` matching is one C call
    that never yields. Measured: the first cut of these tests hung the suite
    until an external timeout killed it.

    A child process can be killed, so a hang becomes an ordinary failure.
    """

    #: Generous by many orders of magnitude -- the point is that the defect
    #: this guards against does not fit in it, not that parsing is fast.
    BUDGET = 20.0

    SCRIPT = (
        "import sys\n"
        "from policy import Policy\n"
        "from policy_builder import PolicyBuilder\n"
        "text = sys.stdin.read()\n"
        "{body}\n"
    )

    def _run(self, body, text):
        import policy_builder
        env = dict(os.environ)
        root = os.path.dirname(os.path.abspath(policy_builder.__file__))
        env['PYTHONPATH'] = os.pathsep.join(
            [root] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
        try:
            done = subprocess.run(
                [sys.executable, '-c', self.SCRIPT.format(body=body)],
                input=text, capture_output=True, text=True,
                timeout=self.BUDGET, env=env)
        except subprocess.TimeoutExpired:
            self.fail(
                "parsing did not finish in %gs. That is the catastrophic "
                "backtracking this guards against: the difference between an "
                "ambiguous pattern and an unambiguous one is exponential, so "
                "there is nothing between milliseconds and forever."
                % self.BUDGET)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()


class TestCommentRunsAreLinear(_Deadline):

    r""" Comments must not cost exponentially (policy_builder.comment_pattern).

    `[ \t]* \# [ \t]* .*` let the second quantifier and `.*` both match the
    blanks after the `#`, so every comment line doubled the number of parses
    the engine had to explore before it could fail. A run of them in front of a
    definition -- i.e. an inventory documented the way everything else in this
    repository is documented -- hung the translator: 20 lines took 2.35s and 24
    took over two minutes, and blank lines made it worse rather than better.
    """

    ROLE = '\n'.join(["describe role Alpha", "\tvlan = 23", "end", ""])
    # `Policy()` ships with the builtin `Internet` role, so the answer is
    # whether the role in the text survived the comment run -- not the whole
    # role set.
    BODY = ("policy = Policy()\n"
            "PolicyBuilder.build_roles_and_services(text, policy)\n"
            "print('Alpha' in policy.roles)")

    def test_a_long_comment_run_before_a_definition_stays_cheap(self):
        comments = '\n'.join('# comment line %d' % i for i in range(40))
        self.assertEqual(
            self._run(self.BODY, '%s\n%s' % (comments, self.ROLE)), 'True')

    def test_blank_separated_comment_blocks_stay_cheap(self):
        """ The shape that measured WORST before the fix: blank lines are
        another alternative in the same group, so they add parses instead of
        resetting anything. Three blocks of 8 took 31.8s. """
        blocks = '\n\n'.join(
            '\n'.join('# block %d line %d' % (b, i) for i in range(8))
            for b in range(3))
        self.assertEqual(
            self._run(self.BODY, '%s\n%s' % (blocks, self.ROLE)), 'True')

    def test_the_comment_language_is_unchanged(self):
        r""" The fix rewrites one pattern into an equivalent one, so every
        shape of comment line that parsed before must still parse: `[ \t]*.*`
        accepts exactly what `.*` accepts. Short enough to run in process --
        it is about meaning, not cost. """
        comments = '\n'.join([
            "#tight",
            "#   padded",
            "   # indented",
            "\t#\ttabbed",
            "#",
            "# trailing blanks   ",
            "  \t #  every \t kind \t of blank ",
        ])
        policy = Policy()
        PolicyBuilder.build_roles_and_services(
            '%s\n%s' % (comments, self.ROLE), policy)
        self.assertIn('Alpha', policy.roles)


class TestAttributeLinesAreLinear(_Deadline):

    r""" The same defect one line further down, driven at the pattern.

    `[ \t]* = [ \t]* %(value)s` overlaps in exactly the same way, because
    `value_pattern` contains a space: each attribute line doubles the search
    space of the role it sits in. Latent rather than live -- no inventory in
    the tree has a role wide enough to notice -- but the same bomb with a
    longer fuse, and 18 lines already measured 0.24s.

    Driven through `role_regex` rather than `build_roles_and_services` because
    the exponent is in the PATTERN: the builder rejects an unknown attribute
    name long before a role gets wide enough to matter, so it cannot reach the
    shape this is about.
    """

    ATTRS = ["\tdescription = 'value %d'" % i for i in range(60)]

    def test_a_wide_role_that_never_closes_stays_cheap(self):
        """ No `end`, so the match must FAIL -- the expensive direction, and
        the one a search scanning past a role takes. """
        text = '\n'.join(["describe role Wide"] + self.ATTRS) + '\n'
        self.assertEqual(
            self._run("print(PolicyBuilder.role_regex.search(text) is None)",
                      text),
            'True')

    def test_a_wide_role_that_does_close_still_parses(self):
        text = '\n'.join(["describe role Wide"] + self.ATTRS + ["end", ""])
        self.assertEqual(
            self._run(
                "m = PolicyBuilder.role_regex.search(text)\n"
                "print(m.group('role_name'), len(PolicyBuilder.match("
                "PolicyBuilder.role_attr_regex, m.group('role_content'), "
                "PolicyBuilder.role_attr_regex.search)))",
                text),
            'Wide 60')


class TestABlankAttributeValueIsRefused(unittest.TestCase):

    r""" The one input whose meaning the fix changes, on purpose.

    `key =   ` with nothing after the blanks used to match, because
    backtracking handed one blank back so `value_pattern` had a character to
    consume -- the attribute's value became a single space. That reading is an
    artifact of the backtracking rather than anything an inventory means, and
    the possessive quantifier that removes the exponent also removes it.

    Recorded as a test rather than a comment because it IS a behaviour change,
    and a behaviour change nobody wrote down is indistinguishable from a
    regression six months later. No inventory in this tree has such a line
    (checked); every real attribute is unaffected.
    """

    def _attr(self, line):
        return PolicyBuilder.role_attr_regex.match(line)

    def test_an_attribute_whose_value_is_only_blanks_no_longer_matches(self):
        self.assertIsNone(self._attr("\tvlan =   \n"))

    def test_an_attribute_with_no_value_at_all_never_matched(self):
        """ The neighbouring case, to show where the boundary actually moved:
        `key =` never matched, because `value_pattern` requires a character and
        a newline is not one. Only the all-blank form changes. """
        self.assertIsNone(self._attr("\tvlan =\n"))

    def test_the_blanks_before_a_real_value_are_still_excluded(self):
        """ What the quantifier is FOR, and why it was made possessive instead
        of deleted: the blanks between `=` and the value stay out of the
        captured value. """
        match = self._attr("\tvlan =    23\n")
        self.assertIsNotNone(match)
        self.assertEqual(match.group('value'), '23')
