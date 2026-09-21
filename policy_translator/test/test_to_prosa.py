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

""" `--prosa` writes the rules, instead of writing nothing (TODO item 20).

`Policy.to_prosa` `print`ed each rule's four raw fields to stdout and then
returned `'\n'.join([])` -- the empty string. So `policy_translator.py -p -o
FILE` created a 0-byte file on every run, and the only output went to a
terminal, in a field order (`from to service operator`) that is not the order
the rule is written in. Found while measuring item 20: the prosa artifact was
byte-identical before and after that change because it was empty both times.

Nothing in the tree consumes prosa, which is why nothing caught it -- this is
the output that exists FOR A HUMAN, so the only thing that could have noticed
was a human reading it.

THREE PROPERTIES, and the last is the one that is easy to leave out.

  1. The file is not empty and every declared rule is in it.
  2. Declaration order, not `set` order. `raw_policies` was a `set`, so even
     once it returned something the order would have changed between runs --
     item 20's defect in a third place. A prosa a reader checks line by line
     against the policy file has to read in the file's order, which is the
     same reason item 18 chose declaration order for a wildcard's services.
  3. **A rule the default policy does not permit is MARKED, not dropped.**
     FPL's three permissions are read only under `default: deny` and its three
     prohibitions only under `default: allow`; the other three reach a
     `PT_LOGGER.debug` and nothing else (`PolicyBuilder.build_policies`). Such
     a rule sits in the file looking effective while contributing nothing, and
     a prosa that silently omitted it would put a second silent skip on top of
     the first -- while a prosa that rendered it as though it applied would be
     worse still, stating a permission the translator never created.

ENGLISH, like the rest of the project. Prosa was written in German to match
the exceptions and `to_html`, which were the last German left in the tree; all
of it was translated in the same breath (owner, 2026-09-21), so there is no
longer a house style pulling the other way. The assertions below name sentence
fragments rather than whole sentences, so a wording change does not turn this
file red for no reason -- the templates are two dicts on `Policy`.
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

_INVENTORY = """
def service SSH
\tprotocol = 'tcp'
\tport = 22
end

def service HTTP
\tprotocol = 'tcp'
\tport = 80
end

def role Zulu
\tipv4 = '10.0.9.0/24'
\toffers SSH
\toffers HTTP
end

def role Alpha
\tipv4 = '10.0.1.0/24'
end

def role Bravo
\tipv4 = '10.0.2.0/24'
end
"""


def _prosa(policies, default='deny', strict=True):
    policy = Policy(strict=strict)
    PolicyBuilder.build(
        "%s\ndef policies (default: %s)\n%send\n" % (
            _INVENTORY, default,
            ''.join('\t%s\n' % rule for rule in policies)),
        policy)
    return policy.to_prosa()


class TestItWritesSomethingAtAll(unittest.TestCase):

    """ THE DEFECT. Each of these fails against `return '\\n'.join([])`. """

    def test_the_result_is_not_empty(self):
        self.assertTrue(_prosa(['Alpha ---> Zulu']).strip())

    def test_the_cli_writes_a_non_empty_file(self):
        """ Through the real CLI, because the defect was in the seam between a
        method that printed and a caller that wrote what it returned. """
        with tempfile.TemporaryDirectory(prefix='prosa_') as directory:
            source = os.path.join(directory, 'policy.txt')
            out = os.path.join(directory, 'out.txt')
            with open(source, 'w', encoding='utf-8') as raw:
                raw.write("%s\ndef policies (default: deny)\n"
                          "\tAlpha ---> Zulu.SSH\nend\n" % _INVENTORY)

            done = subprocess.run(
                [sys.executable, _CLI, '-p', '-o', out, source],
                cwd=_HERE, check=False, capture_output=True, timeout=120)

            self.assertEqual(done.returncode, 0, done.stderr.decode())
            self.assertGreater(
                os.path.getsize(out), 0, "--prosa wrote an empty file")
            with open(out, encoding='utf-8') as raw:
                self.assertIn('Alpha', raw.read())

    def test_every_declared_rule_appears(self):
        text = _prosa(['Alpha ---> Zulu.SSH', 'Bravo <--> Zulu', 'Alpha <->> Bravo'])

        for rule in ('Alpha ---> Zulu.SSH', 'Bravo <--> Zulu', 'Alpha <->> Bravo'):
            self.assertIn(rule, text)

    def test_the_header_states_the_default_policy(self):
        self.assertIn('default: deny', _prosa(['Alpha ---> Zulu']))
        self.assertIn(
            'default: allow', _prosa(['Alpha --/-> Zulu'], default='allow'))

    def test_the_header_counts_the_rules(self):
        self.assertIn('1 rule.', _prosa(['Alpha ---> Zulu']))
        self.assertIn('2 rules.', _prosa(['Alpha ---> Zulu', 'Bravo ---> Zulu']))


class TestDeclarationOrder(unittest.TestCase):

    """ `raw_policies` was a `set`; the names below are chosen so its order
    differs from both declaration order and sorted order under most seeds.

    The two in-process tests here are seed-dependent BY NATURE -- set order is
    fixed once the interpreter starts, so within one process there is nothing
    to vary. Measured with the `set` restored: they go red under 11 of 12
    seeds, which makes them a good statement of the property and a poor gate.
    `test_it_is_reproducible_across_hash_seeds` is the one that cannot miss,
    and it is why this class crosses a process boundary at all.
    """

    _RULES = ['Zulu ---> Alpha', 'Alpha ---> Bravo', 'Bravo ---> Zulu']

    def test_the_rules_read_in_the_order_they_were_written(self):
        text = _prosa(self._RULES)
        positions = [text.index(rule) for rule in self._RULES]

        self.assertEqual(positions, sorted(positions),
                         "prosa does not follow the policy file's order")

    def test_it_is_not_merely_sorted(self):
        """ So a later `sorted()` cannot pass this by accident: declaration
        order here is NOT alphabetical. """
        text = _prosa(self._RULES)
        self.assertLess(text.index('Zulu ---> Alpha'),
                        text.index('Alpha ---> Bravo'))

    def test_a_rule_written_twice_appears_once(self):
        """ The `set` deduplicated and the replacement must too: a redundancy
        is not two rules. """
        text = _prosa(['Alpha ---> Zulu', 'Alpha ---> Zulu'])

        self.assertEqual(text.count('Alpha ---> Zulu'), 1)
        self.assertIn('1 rule.', text)

    def test_it_is_reproducible_across_hash_seeds(self):
        """ Across a process boundary, since hash randomisation is fixed at
        interpreter start. """
        with tempfile.TemporaryDirectory(prefix='prosa_seed_') as directory:
            source = os.path.join(directory, 'policy.txt')
            with open(source, 'w', encoding='utf-8') as raw:
                raw.write("%s\ndef policies (default: deny)\n%send\n" % (
                    _INVENTORY, ''.join('\t%s\n' % r for r in self._RULES)))

            seen = set()
            for seed in ('0', '1', '2', '3', '4', '5', '6', '7'):
                out = os.path.join(directory, 'out.%s.txt' % seed)
                done = subprocess.run(
                    [sys.executable, _CLI, '-p', '-o', out, source],
                    cwd=_HERE, env=dict(os.environ, PYTHONHASHSEED=seed),
                    check=False, capture_output=True, timeout=120)
                self.assertEqual(done.returncode, 0, done.stderr.decode())
                with open(out, encoding='utf-8') as raw:
                    seen.add(raw.read())

            self.assertEqual(len(seen), 1, "prosa differs between hash seeds")


class TestEachOperatorSaysItsOwnThing(unittest.TestCase):

    """ Six operators, six sentences. A shared or missing template would let
    two operators render identically, which is the one thing a prosa must not
    do -- `<-->` and `--->` differ by exactly the direction a reader is
    consulting this output to learn. """

    def test_the_three_permissions(self):
        text = _prosa(['Alpha ---> Zulu', 'Bravo <--> Zulu', 'Alpha <->> Bravo'])

        self.assertIn('Alpha may reach Zulu.', text)
        self.assertIn('Bravo and Zulu may reach each other.', text)
        self.assertIn('replies may come back', text)

    def test_the_three_prohibitions(self):
        text = _prosa(
            ['Alpha --/-> Zulu', 'Bravo <-/-> Zulu', 'Alpha -/->> Bravo'],
            default='allow')

        self.assertIn('Alpha may not reach Zulu.', text)
        self.assertIn('Bravo and Zulu may not reach each other.', text)
        self.assertIn('may not open new connections', text)

    def test_no_two_operators_render_the_same_sentence(self):
        for table in (Policy.prosa_permits, Policy.prosa_forbids):
            self.assertEqual(len(set(table.values())), len(table))

    def test_every_operator_the_grammar_accepts_has_a_sentence(self):
        """ Pinned against the GRAMMAR, so a seventh operator added to FPL
        fails here rather than rendering as a bare source line. """
        import re
        from policy_builder import PolicyBuilder as PB

        # The grammar's own alternation, read out whole rather than matched
        # operator by operator: a pattern loose enough to find them all also
        # found things that are not operators, and a tighter one silently
        # missed `<->>` -- which made this test pass while checking five of
        # the six. Taking the group verbatim cannot be partly right.
        group = re.search(r'\(([^()]*--->[^()]*)\)', PB.policies_regex.pattern)
        self.assertIsNotNone(
            group, "could not find the operator alternation in policies_regex")

        operators = set(group.group(1).split('|'))
        known = set(Policy.prosa_permits) | set(Policy.prosa_forbids)

        self.assertEqual(len(operators), 6, sorted(operators))
        self.assertEqual(
            operators - known, set(),
            "the grammar accepts an operator prosa cannot render")
        self.assertEqual(
            known - operators, set(),
            "prosa renders an operator the grammar does not accept")


class TestAServiceIsNamed(unittest.TestCase):

    def test_a_named_service_appears_in_the_sentence(self):
        text = _prosa(['Alpha ---> Zulu.SSH'])

        self.assertIn('service SSH', text)

    def test_a_rule_without_a_service_names_none(self):
        text = _prosa(['Alpha ---> Zulu'])

        self.assertNotIn('service', text.split('Alpha ---> Zulu')[1])

    def test_a_wildcard_is_not_rendered_as_a_service_called_star(self):
        """ `Zulu.*` means every service Zulu offers, and a reader seeing
        "den Dienst *" would have to know that. """
        text = _prosa(['Alpha ---> Zulu.*'])

        self.assertIn('every service it offers', text)
        self.assertNotIn('service *', text)


class TestARuleTheDefaultIgnoresIsMARKED(unittest.TestCase):

    """ THE PROPERTY THAT IS EASY TO LEAVE OUT. `build_policies` skips these
    with nothing but a debug log, so the policy file and the generated matrix
    disagree and only prosa is positioned to say so. """

    def test_a_permission_under_default_allow_is_marked(self):
        text = _prosa(['Alpha ---> Zulu'], default='allow')

        self.assertIn('Alpha ---> Zulu', text, "the rule was dropped entirely")
        self.assertIn('NO EFFECT', text)
        self.assertIn('default: deny', text)

    def test_a_prohibition_under_default_deny_is_marked(self):
        text = _prosa(['Alpha --/-> Zulu'], default='deny')

        self.assertIn('Alpha --/-> Zulu', text)
        self.assertIn('NO EFFECT', text)
        self.assertIn('default: allow', text)

    def test_it_does_NOT_claim_the_rule_applies(self):
        """ The failure worth ruling out by name: rendering the sentence
        anyway would state a permission the translator never created. """
        text = _prosa(['Alpha ---> Zulu'], default='allow')

        self.assertNotIn('Alpha may reach Zulu.', text)

    def test_an_honoured_rule_is_not_marked(self):
        self.assertNotIn('NO EFFECT', _prosa(['Alpha ---> Zulu']))


class TestItRendersTheAUTHORSRules(unittest.TestCase):

    def test_the_implicit_self_policies_are_absent(self):
        """ `strict=False` adds a self-reachability policy per atomic role.
        They are the translator's, not the author's, and a prosa listing them
        would not match the file it is read against. """
        text = _prosa(['Alpha ---> Zulu'], strict=False)

        self.assertNotIn('Alpha ---> Alpha', text)
        self.assertIn('1 rule.', text)

    def test_a_policy_with_no_rules_still_renders_its_header(self):
        text = _prosa([])

        self.assertIn('default: deny', text)
        self.assertIn('0 rules.', text)


if __name__ == '__main__':
    unittest.main()
