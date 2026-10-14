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

""" iptables/generator.py on hand-built ASTs (no PyBison): the per-rule
translation of interfaces (with VLAN suffixes), IPv4 addresses and multiport
ranges; the snapshot model; and the state-shell interweaving with exactly the
two conntrack states the generator models today, `NEW` and `ESTABLISHED`.

Deliberately NOT here: any other conntrack spelling (`RELATED,ESTABLISHED`,
`INVALID`, ...). TODO.md item 50 records that the generator mishandles those
and that the fix is pending; pinning today's output would pin the defect.

test_generator.py covers the basic non-interweaving translation and the field
swap helpers; this file covers the rest.
"""

import unittest

from iptables.generator import (
    generate, _adjust_ports, _adjust_interfaces, _adjust_action,
    _get_action_from_ast, _get_rules_from_ast,
)
from devices.packet_filter import PacketFilterModel
from devices.snapshot_packet_filter import SnapshotPacketFilterModel
from rule.rule_model import Forward, Match, RuleField
from util.model_util import TABLE_MAX
from util.tree_util import Tree


def _build(tpls):
    """ A Tree from nested tuples; the first element is the node value. """
    if not isinstance(tpls, tuple):
        return Tree(tpls)
    tree = _build(tpls[0])
    for child in tpls[1:]:
        tree.add_child(_build(child))
    return tree


def _ruleset(*commands):
    """ An AST root of ip6tables commands, each (raw line, command subtree);
    the line number is the position. """
    ast = Tree('root')
    for lineno, (raw, body) in enumerate(commands):
        ast.add_child(_build(
            (raw, body, ('-t', ('filter',)), ('--line-no', (str(lineno),)))
        ))
    return ast


def _fields(rule):
    return [(f.name, f.value) for f in rule.match]


def _by_idx(rules):
    return sorted(rules, key=lambda r: r.idx)


class TestRuleTranslation(unittest.TestCase):
    """ One FORWARD chain, interweaving off: each command's translation.

    The port ranges end on a prefix boundary on purpose: for a range whose
    last port is left over on its own (`1:2`, `10:20`),
    `util.packet_util.portrange_to_prefix_list` currently omits that port, and
    this file must not pin that. """

    @classmethod
    def setUpClass(cls):
        ast = _ruleset(
            ('policy', ('-P', ('FORWARD', ('DROP',)))),
            ('vlan', ('-A', ('FORWARD',), ('-i', ('eth0.10',)), ('-o', ('eth1.20',)),
                      ('-s', ('192.0.2.1',)), ('-d', ('198.51.100.0/24',)),
                      ('-j', ('ACCEPT',)))),
            ('plain', ('-A', ('FORWARD',), ('-i', ('eth0',)), ('-o', ('eth1',)),
                       ('-j', ('DROP',)))),
            ('both', ('-A', ('FORWARD',), ('-p', ('tcp',)), ('--sports', ('1024:1027',)),
                      ('--dports', ('80:81',)), ('-j', ('ACCEPT',)))),
            ('product', ('-A', ('FORWARD',), ('-p', ('tcp',)), ('--sports', ('8:23',)),
                         ('--dports', ('80:81',)), ('-j', ('ACCEPT',)))),
            ('sports', ('-A', ('FORWARD',), ('-p', ('tcp',)), ('--sports', ('8:15',)),
                        ('-j', ('ACCEPT',)))),
            ('dports', ('-A', ('FORWARD',), ('-p', ('udp',)), ('--dports', ('4:7',)),
                        ('-j', ('ACCEPT',)))),
        )
        cls.model = generate(ast, 'fw', '192.0.2.254', ['eth0', 'eth1'], interweaving=False)
        cls.rules = _by_idx(cls.model.tables['fw.forward_filter'])
        cls.by_line = {r.raw_line: r for r in cls.rules}

    def test_the_model_is_a_packet_filter_with_its_address(self):
        self.assertIsInstance(self.model, PacketFilterModel)
        self.assertIn(('packet.ipv4.destination', '192.0.2.254'),
                      _fields(self.model.tables['fw.pre_routing'][0]))

    def test_vlan_qualified_interfaces_and_ipv4_addresses(self):
        rule = self.by_line['vlan']
        self.assertEqual(_fields(rule), [
            ('in_port', 'fw.eth0_ingress'), ('out_port', 'fw.eth1_egress'),
            ('packet.ipv4.source', '192.0.2.1'),
            ('packet.ipv4.destination', '198.51.100.0/24'),
            ('packet.ether.svlan', '10'), ('packet.ether.dvlan', '20'),
        ])
        self.assertEqual(rule.actions, [Forward(['fw.forward_filter_accept'])])
        self.assertEqual(rule.in_ports, ['fw.forward_filter_in'])

    def test_plain_interfaces_and_a_drop(self):
        rule = self.by_line['plain']
        self.assertEqual(_fields(rule), [('in_port', 'fw.eth0_ingress'),
                                         ('out_port', 'fw.eth1_egress')])
        self.assertEqual(rule.actions, [])

    def test_sport_and_dport_ranges_expand_to_their_product(self):
        rows = [r for r in self.rules if r.raw_line == 'both']
        self.assertEqual(len(rows), 1)     # 1024-1027 is one prefix, 80-81 one
        self.assertEqual(_fields(rows[0]), [
            ('packet.ipv6.proto', '6'),
            ('packet.upper.sport', '00000100000000xx'),
            ('packet.upper.dport', '000000000101000x'),
        ])

    def test_ranges_of_several_prefixes_expand_to_every_pair(self):
        rows = [r for r in self.rules if r.raw_line == 'product']
        # 8-23 is two prefixes (8-15, 16-23), 80-81 one: two rules, at
        # consecutive indices
        self.assertEqual([_fields(r)[1:] for r in rows], [
            [('packet.upper.sport', '0000000000001xxx'),
             ('packet.upper.dport', '000000000101000x')],
            [('packet.upper.sport', '0000000000010xxx'),
             ('packet.upper.dport', '000000000101000x')],
        ])
        self.assertEqual(rows[1].idx, rows[0].idx + 1)

    def test_a_single_port_range_expands_alone(self):
        sports = [r for r in self.rules if r.raw_line == 'sports']
        dports = [r for r in self.rules if r.raw_line == 'dports']
        self.assertEqual([_fields(r)[-1] for r in sports],
                         [('packet.upper.sport', '0000000000001xxx')])
        self.assertEqual([_fields(r)[-1] for r in dports],
                         [('packet.upper.dport', '00000000000001xx')])
        self.assertEqual(_fields(dports[0])[0], ('packet.ipv6.proto', '17'))

    def test_the_policy_is_last_and_rules_keep_their_order(self):
        self.assertEqual(self.rules[-1].raw_line, 'policy')
        self.assertEqual(self.rules[-1].idx, TABLE_MAX)
        self.assertEqual([r.raw_line for r in self.rules],
                         ['vlan', 'plain', 'both', 'product', 'product',
                          'sports', 'dports', 'policy'])
        self.assertEqual(len({r.idx for r in self.rules}), len(self.rules))


class TestRuleMappings(unittest.TestCase):
    """ `_get_rules_from_ast` also reports, per chain, which rule indices each
    source line expanded to. """

    def test_a_multiport_line_maps_to_all_its_rules(self):
        ast = _ruleset(
            ('mp', ('-A', ('INPUT',), ('-p', ('tcp',)), ('--dports', ('8:23',)),
                    ('-j', ('ACCEPT',)))),
        )
        chains = _get_rules_from_ast('fw', ast)
        rules = chains['input_filter']
        mappings = chains['input_filter_mappings']
        self.assertEqual(len(rules), 2)    # 8-15 and 16-23
        self.assertEqual(mappings['expanded'], {'0': sorted(rules)})
        self.assertEqual(set(mappings['original']), set(rules))


    def test_nothing_to_translate(self):
        self.assertEqual(_get_rules_from_ast('fw', Tree('leaf')), {})
        self.assertEqual(_get_rules_from_ast('fw', _ruleset(('empty', ('-A',)))), {})


class TestSnapshotGeneration(unittest.TestCase):
    """ `state_snap` builds a snapshot packet filter, never interwoven. """

    def test_snapshot_model(self):
        ast = _ruleset(
            ('policy', ('-P', ('FORWARD', ('ACCEPT',)))),
            ('deny', ('-A', ('FORWARD',), ('-d', ('2001:db8::1',)), ('-j', ('DROP',)))),
        )
        model = generate(ast, 'fw', '2001:db8::fe', ['1', '2'], state_snap=True)
        self.assertIsInstance(model, SnapshotPacketFilterModel)
        rules = _by_idx(model.tables['fw.forward_filter'])
        self.assertEqual([(r.raw_line, r.actions) for r in rules],
                         [('deny', []), ('policy', [Forward(['fw.forward_filter_accept'])])])
        self.assertEqual(len(model.tables['fw.forward_state']), 1)


class TestStateShellInterweaving(unittest.TestCase):
    """ The state shell, with `--ctstate NEW` and `--ctstate ESTABLISHED` only.

    A NEW rule gains `related=0`. An ESTABLISHED rule is replaced by the
    reverse chain's rules, swapped in direction, tagged `related=1` and
    adjusted to this chain's ports; then the remaining rules follow. Conntrack
    fields never survive into the model. """

    @classmethod
    def setUpClass(cls):
        ast = _ruleset(
            ('p-in', ('-P', ('INPUT', ('DROP',)))),
            ('p-out', ('-P', ('OUTPUT', ('DROP',)))),
            ('p-fwd', ('-P', ('FORWARD', ('DROP',)))),
            ('in-ssh', ('-A', ('INPUT',), ('-p', ('tcp',)), ('--dport', ('22',)),
                        ('-m', ('conntrack',)), ('--ctstate', ('NEW',)),
                        ('-j', ('ACCEPT',)))),
            ('in-est', ('-A', ('INPUT',), ('-m', ('conntrack',)),
                        ('--ctstate', ('ESTABLISHED',)), ('-j', ('ACCEPT',)))),
            ('out-est', ('-A', ('OUTPUT',), ('-m', ('conntrack',)),
                         ('--ctstate', ('ESTABLISHED',)), ('-j', ('ACCEPT',)))),
            ('out-web', ('-A', ('OUTPUT',), ('-o', ('eth1',)), ('-p', ('tcp',)),
                         ('--dport', ('80',)), ('-j', ('ACCEPT',)))),
            ('fwd-est', ('-A', ('FORWARD',), ('-m', ('conntrack',)),
                         ('--ctstate', ('ESTABLISHED',)), ('-j', ('ACCEPT',)))),
            ('fwd-x', ('-A', ('FORWARD',), ('-i', ('eth0',)), ('-d', ('2001:db8::1',)),
                       ('-j', ('ACCEPT',)))),
        )
        cls.model = generate(ast, 'fw', None, ['eth0', 'eth1'], interweaving=True)

    def _table(self, chain):
        return [(_fields(r), r.actions, r.raw_line)
                for r in _by_idx(self.model.tables['fw.' + chain])]

    def test_input_chain(self):
        accept = [Forward(['fw.input_filter_accept'])]
        self.assertEqual(self._table('input_filter'), [
            # the NEW rule, conditioned on related=0
            ([('packet.ipv6.proto', '6'), ('packet.upper.dport', '22'),
              ('related', '0')], accept, 'in-ssh'),
            # the ESTABLISHED rule becomes OUTPUT's rules reversed: a reply
            # to out-web is accepted, everything else OUTPUT drops is dropped
            ([('in_port', 'fw.eth1_ingress'), ('packet.ipv6.proto', '6'),
              ('packet.upper.sport', '80'), ('related', '1')], accept, None),
            ([('related', '1')], [], None),
            ([], [], 'p-in'),
        ])

    def test_output_chain(self):
        self.assertEqual(self._table('output_filter'), [
            ([('related', '1')], [], None),
            ([('out_port', 'fw.eth1_egress'), ('packet.ipv6.proto', '6'),
              ('packet.upper.dport', '80')],
             [Forward(['fw.output_filter_accept'])], 'out-web'),
            ([], [], 'p-out'),
        ])

    def test_forward_chain_reverses_itself(self):
        accept = [Forward(['fw.forward_filter_accept'])]
        self.assertEqual(self._table('forward_filter'), [
            ([('out_port', 'fw.eth0_egress'), ('packet.ipv6.source', '2001:db8::1'),
              ('related', '1')], accept, None),
            ([('related', '1')], [], None),
            ([('in_port', 'fw.eth0_ingress'), ('packet.ipv6.destination', '2001:db8::1')],
             accept, 'fwd-x'),
            ([], [], 'p-fwd'),
        ])

    def test_no_conntrack_field_survives(self):
        for table, rules in self.model.tables.items():
            for rule in rules:
                self.assertNotIn('module.conntrack.ctstate',
                                 [f.name for f in rule.match], table)


class TestDroppingStateCheck(unittest.TestCase):
    """ `--ctstate ESTABLISHED -j DROP`: the state-checking rule has no action
    (the generator's DROP is `[]`), and interweaving once indexed its first
    action and raised IndexError (TODO item 53, fixed upstream in 996a4b77).
    Now every reverse-chain rule is tagged `related=1` and drops, with the
    shell's own drop `Forward([])`. """

    def test_established_drop_makes_the_whole_state_shell_drop(self):
        ast = _ruleset(
            ('p-fwd', ('-P', ('FORWARD', ('DROP',)))),
            ('fwd-est', ('-A', ('FORWARD',), ('-m', ('conntrack',)),
                         ('--ctstate', ('ESTABLISHED',)), ('-j', ('DROP',)))),
            ('fwd-x', ('-A', ('FORWARD',), ('-i', ('eth0',)), ('-d', ('2001:db8::1',)),
                       ('-j', ('ACCEPT',)))),
        )
        model = generate(ast, 'fw', None, ['eth0', 'eth1'], interweaving=True)
        table = [(_fields(r), r.actions, r.raw_line)
                 for r in _by_idx(model.tables['fw.forward_filter'])]
        self.assertEqual(table, [
            ([('out_port', 'fw.eth0_egress'), ('packet.ipv6.source', '2001:db8::1'),
              ('related', '1')], [Forward([])], None),
            ([('related', '1')], [Forward([])], None),
            ([('in_port', 'fw.eth0_ingress'), ('packet.ipv6.destination', '2001:db8::1')],
             [Forward(['fw.forward_filter_accept'])], 'fwd-x'),
            ([], [], 'p-fwd'),
        ])


class TestAdjustHelpers(unittest.TestCase):
    """ Moving a reversed rule into the chain it is woven into. """

    def test_ports(self):
        ports = ['fw.output_filter_accept', 'fw.input_filter_accept']
        self.assertIs(_adjust_ports(ports, 'forward_filter'), ports)
        self.assertEqual(_adjust_ports(ports, 'input_filter'),
                         ['fw.input_filter_accept'] * 2)
        self.assertEqual(_adjust_ports(ports, 'output_filter'),
                         ['fw.output_filter_accept'] * 2)
        with self.assertRaisesRegex(Exception, 'unknown chain: routing'):
            _adjust_ports(ports, 'routing')

    def test_interfaces(self):
        def adjusted(chain):
            match = Match([RuleField('in_port', 'fw.1_egress'),
                           RuleField('out_port', 'fw.2_ingress'),
                           RuleField('packet.upper.dport', '80')])
            return [(f.name, f.value) for f in _adjust_interfaces(match, chain)]

        self.assertEqual(adjusted('forward_filter'),
                         [('in_port', 'fw.1_egress'), ('out_port', 'fw.2_ingress'),
                          ('packet.upper.dport', '80')])
        self.assertEqual(adjusted('input_filter')[:2],
                         [('in_port', 'fw.1_ingress'), ('out_port', 'fw.2_ingress')])
        self.assertEqual(adjusted('output_filter')[:2],
                         [('in_port', 'fw.1_egress'), ('out_port', 'fw.2_egress')])

    def test_action(self):
        self.assertEqual(_adjust_action(Forward(['fw.output_filter_accept']), 'input_filter'),
                         Forward(['fw.input_filter_accept']))
        self.assertEqual(_adjust_action(Forward([]), 'input_filter'), Forward([]))

    def test_the_action_of_a_policy_is_its_target(self):
        ast = _build(('-P', ('FORWARD', ('DROP',))))
        self.assertEqual(_get_action_from_ast(ast), 'DROP')


if __name__ == '__main__':
    unittest.main()
