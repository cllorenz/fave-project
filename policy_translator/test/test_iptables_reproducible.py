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

""" A generated rule set is the SAME rule set on the next run (TODO item 20).

It was not. `Policy.get_atomic_roles` returns a `set`, and set iteration for
strings follows a hash Python randomises per process, so `to_iptables` emitted
its rules in a different order from one run to the next. Measured on
`_INVENTORY` below before the fix: eight `PYTHONHASHSEED` values produced SEVEN
different files.

**NOTHING WAS EVER WRONG, and that is the point of the second half of this
file.** Per the thesis (Sec. 7.3, Algorithm 7.1) a rule set is a composition of
blocks emitted in a fixed order, and a block whose order can vary is
single-action -- every rule in it carries the same `-j` target, so a packet
matching several of them gets the same verdict whichever matches first. The
reordering was confined to such blocks, checked across seeds. What it cost was
the ARTIFACT: a firewall that cannot be checksummed, diffed against the
previous run, or reviewed by eye without the reader first deciding which
differences mean anything. CLOUD_BENCH_PLAN.md §1.8 wants every artifact
recreatable from its raw data, and byte-identical is the useful form of that.

THREE SITES, and the third is the one that hides. `to_iptables` iterates the
atomic roles twice, for the two anti-spoofing blocks. The third is in
`policy_builder.build_policies`, which adds the default self-reachability
policies over the same set: that reorders INSERTION into `Policy.policies`,
which `to_iptables` then walks to emit its Access Rules block. A set in one
module moved rules in a file emitted by another. The CSV, the prosa and the
roles JSON are unaffected -- measured across eight seeds, one output each --
because they iterate `roles` or sort for themselves, which is why the
artifact-invariant tests (item 14) never caught this.

WHY `sorted()` HERE AND DECLARATION ORDER IN ITEM 18. A wildcard's services
are a list the author wrote on the page, so reordering them would be a silent
edit of their text (`test_wildcard_service_order.py`). These are roles the
generator visits, which no one wrote in any order, so any total order will do
and the cheapest reproducible one is the right choice.
"""

import os
import subprocess
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from policy import Policy
from policy_builder import PolicyBuilder
from test_to_iptables import (
    CANON_ORDER,
    H_ACCESS,
    H_SUPPRESS,
    H_V4_ANTISPOOF,
    H_V4_DEFAULT,
    H_V4_STATE,
    H_V6_ANTISPOOF,
    H_V6_DEFAULT,
    H_V6_HARDENING,
    H_V6_ICMP,
    H_V6_STATE,
    parse_blocks,
)


_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_HERE, 'policy_translator.py')

#: Five roles whose names are deliberately NOT in the order they are declared
#: and NOT in address order, so a `set` of them differs between practically any
#: two hash seeds. Every role carries both an `ipv4` and an `ipv6` so both
#: anti-spoofing blocks are populated, and two policies plus the implicit
#: self-reachability fill the Access Rules block.
_INVENTORY = """
def service SSH
\tprotocol = 'tcp'
\tport = 22
end

def role Zulu
\tipv4 = '10.0.9.0/24'
\tipv6 = 'fd00:9::/64'
\toffers SSH
end

def role Alpha
\tipv4 = '10.0.1.0/24'
\tipv6 = 'fd00:1::/64'
end

def role Mike
\tipv4 = '10.0.5.0/24'
\tipv6 = 'fd00:5::/64'
end

def role Bravo
\tipv4 = '10.0.2.0/24'
\tipv6 = 'fd00:2::/64'
end

def role Yankee
\tipv4 = '10.0.8.0/24'
\tipv6 = 'fd00:8::/64'
end

def policies (default: %s)
\tAlpha\t\t\t\t---> Zulu.SSH
\tBravo\t\t\t\t---> Zulu.SSH
end
"""


def _rule_set(default='deny', strict=False):
    policy = Policy(strict=strict)
    policy.default_policy = default == 'allow'
    PolicyBuilder.build(_INVENTORY % default, policy)
    return policy.to_iptables()


def _target(rule):
    """ The `-j X` a rule jumps to, or None for a rule that names no target
    (`-P FORWARD ACCEPT`, `ip6tables -N routinghdr`). """
    fields = rule.split()
    return fields[fields.index('-j') + 1] if '-j' in fields else None


class TestTheRuleSetIsReproducible(unittest.TestCase):

    """ THE ARTIFACT PROPERTY. Hash randomisation is fixed when the interpreter
    starts, so this has to cross a process boundary -- an in-process loop
    cannot exercise it at all, and would pass against the defect. """

    _SEEDS = ('0', '1', '2', '3', '4', '5', '6', '7', '11', '42', '97', '1234')

    def _firewall(self, seed, directory):
        inventory = os.path.join(directory, 'inventory.txt')
        out = os.path.join(directory, 'out.%s.txt' % seed)
        done = subprocess.run(
            [sys.executable, _CLI, '-fw', '-o', out, inventory],
            cwd=_HERE, env=dict(os.environ, PYTHONHASHSEED=seed),
            check=False, capture_output=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr.decode())
        with open(out, encoding='utf-8') as raw:
            return raw.read()

    def test_every_seed_produces_the_same_bytes(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='iptables_repro_') as directory:
            with open(os.path.join(directory, 'inventory.txt'), 'w',
                      encoding='utf-8') as raw:
                raw.write(_INVENTORY % 'deny')

            first = self._firewall(self._SEEDS[0], directory)
            for seed in self._SEEDS[1:]:
                self.assertEqual(
                    first, self._firewall(seed, directory),
                    "PYTHONHASHSEED=%s produced a different rule set" % seed)

    def test_the_anti_spoofing_blocks_are_in_role_order(self):
        """ Not merely stable but stable at a stated order, so "reproducible"
        cannot be satisfied by some incidental order that changes again the
        next time the traversal is touched. """
        blocks = dict(parse_blocks(_rule_set()))

        for header in (H_V4_ANTISPOOF, H_V6_ANTISPOOF):
            addresses = [rule.split(' -s ')[1].split()[0]
                         for rule in blocks[header]]
            self.assertEqual(addresses, sorted(addresses), header)

    def test_the_access_rules_block_keeps_declaration_order_then_sorts(self):
        """ The third site, and the shape it settles on is worth stating.

        `build_policies` inserts the DECLARED policies first, in the order the
        author wrote them, then appends the implicit self-reachability ones
        over the atomic roles. `to_iptables` walks that insertion order. So
        sorting the set fixes the generated tail WITHOUT touching the author's
        own order -- the same division item 18 drew, where a wildcard's
        services keep declaration order because someone wrote them down and
        these are sorted because nobody did.
        """
        pairs = [rule.split('--comment "')[1].split('"')[0]
                 for rule in dict(parse_blocks(_rule_set()))[H_ACCESS]
                 if '--comment "' in rule]
        # Each pair appears twice, once for iptables and once for ip6tables.
        pairs = [pair for index, pair in enumerate(pairs)
                 if index == 0 or pair != pairs[index - 1]]

        declared = ['Alpha to Zulu', 'Bravo to Zulu']
        self.assertEqual(pairs[:len(declared)], declared,
                         "the declared rules lost the author's order")

        generated = pairs[len(declared):]
        self.assertEqual(generated, sorted(generated),
                         "the generated self-policies are not in role order")
        self.assertEqual(
            generated,
            ['Alpha to Alpha', 'Bravo to Bravo', 'Mike to Mike',
             'Yankee to Yankee', 'Zulu to Zulu'])


class TestTheBlocksThatMayBeREORDEREDAreSingleAction(unittest.TestCase):

    r""" THE SAFETY ARGUMENT, WHICH NOTHING USED TO ENFORCE.

    Sorting makes the generator reproducible; it does not make intra-block
    order IRRELEVANT. That is a separate property -- the one Algorithm 7.1
    rests on, and the one that lets `test_to_iptables.py` compare a block as a
    multiset -- and it holds only while a block that can be reordered is
    single-action.

    It is NOT true of every block: `# === IPv6 Hardening ===` mixes DROP,
    RETURN and a jump to `routinghdr`, and there the order genuinely matters
    (the `--rt-segsleft` RETURNs must precede the catch-all DROP). It is safe
    because that block is a fixed literal list nothing permutes -- a different
    reason, so it is classified separately rather than waved at.

    WHAT THIS CATCHES. `jumptarget` is computed from `default_policy` alone, so
    every Access Rules rule carries the same target today. The obvious future
    change -- an explicit deny that emits `-j DROP` beside the permissions --
    would make that block mixed, and its order would silently start to matter
    while `test_to_iptables.py` went on comparing it as a multiset. Then this
    test is the one that says so.
    """

    #: Built from the policy: how many rules and in what order depends on the
    #: input, so these must be single-action.
    ORDER_FREE = (H_SUPPRESS, H_V4_ANTISPOOF, H_V6_ANTISPOOF, H_ACCESS)

    #: Emitted as written, identically on every run. Order is meaningful and
    #: safe because nothing can permute a literal.
    FIXED_LITERAL = (H_V6_ICMP, H_V6_HARDENING)

    #: One rule each, so the question does not arise.
    SINGLETON = (H_V4_DEFAULT, H_V4_STATE, H_V6_DEFAULT, H_V6_STATE)

    def test_every_order_free_block_carries_ONE_target(self):
        for default in ('deny', 'allow'):
            blocks = dict(parse_blocks(_rule_set(default=default)))
            for header in self.ORDER_FREE:
                targets = {_target(rule) for rule in blocks[header]}
                self.assertLessEqual(
                    len(targets), 1,
                    "%s is MIXED under `default: %s` (%s). Its order now "
                    "decides verdicts, so it may no longer be emitted from a "
                    "set nor compared as a multiset." % (
                        header, default, sorted(map(str, targets))))

    def test_the_hardening_block_is_mixed_and_that_is_why_it_is_apart(self):
        """ Inverted on purpose. If this ever goes green by the block becoming
        single-action, the classification above has drifted from the file. """
        blocks = dict(parse_blocks(_rule_set()))
        targets = {_target(rule) for rule in blocks[H_V6_HARDENING]}

        self.assertGreater(
            len(targets), 1,
            "IPv6 Hardening is no longer mixed; move it to ORDER_FREE")

    def test_every_block_is_classified(self):
        """ So a block added later cannot inherit a safety argument nobody
        made for it: it fails here until someone says which kind it is. """
        classified = set(self.ORDER_FREE + self.FIXED_LITERAL + self.SINGLETON)

        self.assertEqual(
            set(CANON_ORDER), classified,
            "a block is in CANON_ORDER but classified in neither kind")
        self.assertEqual(
            [header for header, _rules in parse_blocks(_rule_set())],
            CANON_ORDER,
            "the generator emits blocks this file does not know about")

    def test_a_singleton_block_really_holds_at_most_one_rule(self):
        blocks = dict(parse_blocks(_rule_set()))
        for header in self.SINGLETON:
            self.assertLessEqual(len(blocks[header]), 1, header)


if __name__ == '__main__':
    unittest.main()
