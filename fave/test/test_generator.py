#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" Tests the iptables-AST -> firewall-model generator.

The generator is decoupled from the (pybison) parser: it consumes an in-memory
Tree, so these tests build the AST by hand and run in the fast tier. They cover
the non-interweaving translation in detail and the conntrack state-shell
interweaving path structurally.
"""

import unittest

from util.tree_util import Tree
from rule.rule_model import Forward
from iptables.generator import generate

_FILTER_TABLES = {
    'fw.pre_routing', 'fw.input_filter', 'fw.output_filter',
    'fw.forward_filter', 'fw.routing', 'fw.post_routing', 'fw.internals',
}


def _build(tpls):
    """ Builds a Tree from nested tuples; first element is the node value. """
    if not isinstance(tpls, tuple):
        return Tree(tpls)
    tree = _build(tpls[0])
    for child in tpls[1:]:
        tree.add_child(_build(child))
    return tree


def _command(raw, body, lineno):
    """ Builds one ip6tables command subtree (body + table + line number). """
    return _build((raw, tuple(body), ('-t', ('filter',)), ('--line-no', (str(lineno),))))


class TestGenerateNonInterweaving(unittest.TestCase):
    """ Tests the plain AST -> model translation (interweaving disabled). """

    def setUp(self):
        ast = Tree('root')
        ast.add_child(_command(
            'ip6tables -P FORWARD DROP',
            [('-P', ('FORWARD', ('DROP',)))], 0
        ))
        ast.add_child(_command(
            'ip6tables -A FORWARD -d 2001:db8::1 -j ACCEPT',
            [('-A', ('FORWARD',), ('-d', ('2001:db8::1',)), ('-j', ('ACCEPT',)))], 1
        ))
        self.model = generate(ast, 'fw', None, ['1', '2'], interweaving=False)

    def test_builds_the_filter_pipeline_tables(self):
        self.assertEqual(set(self.model.tables.keys()), _FILTER_TABLES)

    def test_forward_filter_has_policy_and_rule(self):
        fwd = self.model.tables['fw.forward_filter']
        # Two rules: the explicit ACCEPT and the default-DROP policy.
        self.assertEqual(len(fwd), 2)

    def test_default_drop_policy_is_a_low_priority_dropping_rule(self):
        fwd = self.model.tables['fw.forward_filter']
        policy = [r for r in fwd if not r.actions]
        self.assertEqual(len(policy), 1)
        # The policy sits at the lowest priority (largest index).
        self.assertEqual(policy[0].idx, max(r.idx for r in fwd))

    def test_accept_rule_forwards_and_keeps_its_match(self):
        fwd = self.model.tables['fw.forward_filter']
        accept = [r for r in fwd if r.actions]
        self.assertEqual(len(accept), 1)
        rule = accept[0]
        self.assertTrue(any(isinstance(a, Forward) for a in rule.actions))
        self.assertIn(
            ('packet.ipv6.destination', '2001:db8::1'),
            [(f.name, f.value) for f in rule.match]
        )


class TestGenerateInterweaving(unittest.TestCase):
    """ Structural coverage of the conntrack state-shell interweaving path.

    The interweaving cross-references the INPUT and OUTPUT chains, so a ruleset
    must define both. We assert the path runs and yields a coherent model
    rather than pinning the (intricate) exact shell layout.
    """

    def _conntrack_ast(self):
        ast = Tree('root')
        ast.add_child(_command('p-in', [('-P', ('INPUT', ('DROP',)))], 0))
        ast.add_child(_command('p-out', [('-P', ('OUTPUT', ('DROP',)))], 1))
        ast.add_child(_command(
            'in-established',
            [('-A', ('INPUT',), ('-m', ('state',)),
              ('--state', ('ESTABLISHED,RELATED',)), ('-j', ('ACCEPT',)))], 2
        ))
        ast.add_child(_command(
            'in-ssh',
            [('-A', ('INPUT',), ('-p', ('tcp',)),
              ('--dport', ('22',)), ('-j', ('ACCEPT',)))], 3
        ))
        ast.add_child(_command(
            'out-established',
            [('-A', ('OUTPUT',), ('-m', ('state',)),
              ('--state', ('ESTABLISHED,RELATED',)), ('-j', ('ACCEPT',)))], 4
        ))
        ast.add_child(_command('out-any', [('-A', ('OUTPUT',), ('-j', ('ACCEPT',)))], 5))
        return ast

    def test_interweaving_produces_a_coherent_model(self):
        model = generate(self._conntrack_ast(), 'fw', None, ['1', '2'], interweaving=True)
        self.assertEqual(set(model.tables.keys()), _FILTER_TABLES)
        self.assertTrue(model.tables['fw.input_filter'])
        self.assertTrue(model.tables['fw.output_filter'])

    def test_interweaving_does_not_drop_rules_versus_plain(self):
        ast = self._conntrack_ast()
        plain = generate(ast, 'fw', None, ['1', '2'], interweaving=False)
        # Rebuild: generate mutates the AST, so use a fresh one.
        woven = generate(self._conntrack_ast(), 'fw', None, ['1', '2'], interweaving=True)
        self.assertGreaterEqual(
            len(woven.tables['fw.input_filter']),
            len(plain.tables['fw.input_filter'])
        )


if __name__ == '__main__':
    unittest.main()
