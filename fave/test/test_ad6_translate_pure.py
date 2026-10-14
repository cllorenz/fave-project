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

""" `fave/ad6/translate.py` without a solver: the fast-tier half of its tests.

`test_ad6_translate.py` is integration-tier because some of its tests SOLVE a
model, and pycosat has no wheel. Nearly all of the translator, though, is a
pure value -> value map from `rule_model` objects to lxml elements, and its
refusals, orderings and key spellings are decidable without ever building a
SAT instance. This module pins those, on small hand-built models, so a change
to the translator is caught by the tier that runs on every push.

What is pinned, by group:

  * the FIELD layer -- which ad6 element each FaVe field becomes, and every
    REFUSAL (`UnsupportedField`) that keeps a weaker model from being emitted
    silently;
  * the RULE and TABLE layers -- per-port fanout, rewrites riding on every
    jump, the hairpin exclusion, `idx` and declared-LPM ordering;
  * the PORT GRAPH -- splitting, dense ids, per-port chains, edges, and the
    ambiguities it refuses rather than resolves arbitrarily;
  * the whole-model entry points -- `model_to_config`, `instantiate_base`
    (which builds the CNF but does not solve it, so it needs no pycosat),
    generators/probes, and the bridge's query-field recipes.
"""

import unittest

import lxml.etree as et

from ad6 import translate
from ad6.translate import (
    PortGraph, UnsupportedAction, UnsupportedField, field_to_match,
    model_to_config, rule_to_ad6, table_to_ad6,
)
from rule.rule_model import Forward, Match, Miss, Rewrite, Rule, RuleField


def _xml(element):
    return None if element is None else et.tostring(element).decode()


def _fm(name, value, negated=False, mutable=()):
    return _xml(field_to_match(RuleField(name, value, negated), mutable=mutable))


def _rule(idx=0, match=(), actions=(), in_ports=None, node='d', table='d.t'):
    return Rule(node, table, idx, in_ports=in_ports, match=Match(list(match)),
                actions=list(actions))


def _target(port):
    return 'T_' + str(port).replace('.', '_')


_IDS = {'d.1': 1, 'd.2': 2, 'd.3': 3}


def _port_id(port):
    return _IDS[str(port)]


# --- the field layer -------------------------------------------------------

class TestTransportPorts(unittest.TestCase):
    """ `_port_value`: a FaVe port is a decimal or a bit-vector; ad6 takes a
    decimal or `value/prefix`. Anything that would WIDEN the match is refused. """

    def test_a_decimal_passes_through(self):
        self.assertEqual(_fm('packet.upper.dport', '22'),
                         '<port direction="dst">22</port>')

    def test_a_trailing_dont_care_mask_becomes_value_slash_prefix(self):
        # 1xxx...x (16 bits) is 32768-65535: one fixed bit.
        self.assertEqual(_fm('packet.upper.sport', '1' + 'x' * 15),
                         '<port direction="src">32768/1</port>')

    def test_an_all_dont_care_port_constrains_nothing(self):
        self.assertIsNone(field_to_match(RuleField('packet.upper.dport', 'x' * 16)))

    def test_an_interior_dont_care_is_refused(self):
        with self.assertRaises(UnsupportedField) as ctx:
            field_to_match(RuleField('packet.upper.dport', '0x' + '0' * 14))
        self.assertIn('INTERIOR', str(ctx.exception))

    def test_a_non_numeric_port_is_refused(self):
        with self.assertRaises(UnsupportedField):
            translate._port_value('ssh')

    def test_negation_is_kept(self):
        self.assertIn('negated="true"', _fm('packet.upper.dport', '80', negated=True))

    def test_a_FULLY_DETERMINED_port_bit_vector_means_the_same_port_as_in_fave(self):
        """ FaVe's own encoder (`field_value_to_bitvector`, what NetPlumber is
        fed) reads the 16-character value `0000000000010100` as BINARY: port 20,
        bit-for-bit the vector it builds for `'20'`. `_port_value` once tested
        `isdigit()` first and passed it through as DECIMAL, which ad6's
        CanonizePort turned into port 10,100 (TODO item 53). """
        self.assertEqual(_fm('packet.upper.dport', '0000000000010100'),
                         _fm('packet.upper.dport', '20'))
        # Fewer than 16 characters is not a port vector to FaVe: decimal.
        self.assertEqual(_fm('packet.upper.dport', '10100'), '<port direction="dst">10100</port>')

class TestProtocolAndIcmp6Names(unittest.TestCase):
    """ ad6 looks protocols and ICMPv6 types up BY NAME and silently returns a
    wrong code on a miss, so the translator maps and refuses. """

    def test_fave_protocol_numbers_are_turned_back_into_names(self):
        self.assertEqual(_fm('packet.ipv6.proto', 'udp'), '<proto>udp</proto>')
        self.assertEqual(_fm('packet.ipv6.proto', '58'), '<proto>icmp6</proto>')

    def test_a_protocol_without_a_name_in_ad6s_table_is_refused(self):
        with self.assertRaises(UnsupportedField) as ctx:
            field_to_match(RuleField('packet.ipv6.proto', '47'))
        self.assertIn("'47'", str(ctx.exception))

    def test_british_icmp6_spellings_become_ad6s_american_ones(self):
        self.assertIn('neighbor-solicitation',
                      _fm('packet.ipv6.icmpv6.type', 'neighbour-solicitation'))

    def test_a_shared_icmp6_name_passes_through_with_negation(self):
        out = _fm('packet.ipv6.icmpv6.type', 'echo-request', negated=True)
        self.assertIn('echo-request', out)
        self.assertIn('negated="true"', out)

    def test_an_unknown_icmp6_type_is_refused(self):
        with self.assertRaises(UnsupportedField):
            field_to_match(RuleField('packet.ipv6.icmpv6.type', 'no-such-type'))


class TestNormalisedAndTernaryValues(unittest.TestCase):
    """ Fields FaVe normalises to a number reuse FaVe's own encoding; non-integer
    values of node-scoped fields become ternary bit-vectors of FaVe's width. """

    def test_a_rate_is_encoded_as_faves_number(self):
        self.assertEqual(_fm('module.limit', '900/min'),
                         '<fieldmatch field="module.limit">54000</fieldmatch>')

    def test_a_header_name_is_encoded_as_its_protocol_number(self):
        self.assertEqual(_fm('module.ipv6header.header', 'ipv6-route'),
                         '<fieldmatch field="module.ipv6header.header">43</fieldmatch>')

    def test_a_normalised_value_with_dont_cares_is_refused(self):
        with self.assertRaises(UnsupportedField):
            translate._normalised_value('module.limit', 'x')

    def test_a_mutable_cidr_becomes_a_prefix_ternary(self):
        self.assertEqual(
            _fm('packet.ipv4.destination', '10.0.0.0/8',
                mutable={'packet.ipv4.destination'}),
            '<fieldmatch field="packet.ipv4.destination">b00001010%s</fieldmatch>'
            % ('x' * 24))

    def test_a_generic_dont_care_vlan_becomes_a_ternary_on_ad6s_name(self):
        self.assertEqual(_fm('packet.ether.vlan', '00000000000001xx'),
                         '<fieldmatch field="vlan">b00000000000001xx</fieldmatch>')

    def test_an_integer_generic_value_stays_decimal(self):
        self.assertEqual(_fm('related', '1'),
                         '<fieldmatch field="related">1</fieldmatch>')

    def test_a_field_fave_declares_no_width_for_is_refused(self):
        with self.assertRaises(UnsupportedField) as ctx:
            translate._ternary_text('no.such.field', '1x')
        self.assertIn('FIELD_SIZES', str(ctx.exception))

    def test_a_value_fave_cannot_encode_is_refused_by_name(self):
        with self.assertRaises(UnsupportedField) as ctx:
            translate._ternary_text('packet.ether.vlan', 'abc')
        self.assertIn('cannot encode', str(ctx.exception))

    def test_a_vector_of_the_wrong_width_is_refused(self):
        with self.assertRaises(UnsupportedField) as ctx:
            translate._ternary_text('packet.ether.vlan', 'x1xx')
        self.assertIn('16 wide', str(ctx.exception))


class TestFieldToMatchDispatch(unittest.TestCase):

    def test_match_all_addresses_produce_nothing(self):
        for value in ('0.0.0.0/0', '::/0'):
            with self.subTest(value=value):
                name = ('packet.ipv6.source' if ':' in value
                        else 'packet.ipv4.source')
                self.assertIsNone(field_to_match(RuleField(name, value)))

    def test_a_negated_match_all_is_kept_because_it_is_the_empty_set(self):
        self.assertIsNotNone(
            field_to_match(RuleField('packet.ipv4.source', '0.0.0.0/0', True)))

    def test_an_immutable_address_is_a_typed_primitive(self):
        self.assertEqual(
            _fm('packet.ipv6.destination', '2001:db8::/32'),
            '<ip version="6" direction="dst"><address>2001:db8::/32</address></ip>')

    def test_a_fully_determined_vlan_vector_means_the_same_vlan_as_in_fave(self):
        """ A mutable field takes the decimal path for an integer. A
        16-character 0/1 string is a bit-vector to FaVe, so it must reach ad6
        as the integer it spells: VLAN 5, not 101 (TODO item 53). """
        mutable = {'packet.ether.vlan'}
        self.assertEqual(_fm('packet.ether.vlan', '0000000000000101', mutable=mutable),
                         _fm('packet.ether.vlan', '5', mutable=mutable))

    def test_port_fields_are_refused_at_the_field_layer(self):
        for name in ('in_port', 'out_port'):
            with self.subTest(field=name):
                with self.assertRaises(UnsupportedField):
                    field_to_match(RuleField(name, 'd.1'))

    def test_an_unknown_field_is_refused_and_named(self):
        with self.assertRaises(UnsupportedField) as ctx:
            field_to_match(RuleField('packet.ether.type', '1'))
        self.assertIn('packet.ether.type', str(ctx.exception))

    def test_simple_typed_fields(self):
        self.assertTrue(_fm('packet.upper.tcp.flags', '1xxxxxxx').startswith('<tcp-flags'))
        self.assertIsNotNone(_fm('module.ipv6header.rt.type', '0'))
        self.assertIsNotNone(_fm('module.ipv6header.rt.segsleft', '0'))

    def test_supported_fields_is_the_union_of_the_tables(self):
        fields = translate.supported_fields()
        self.assertTrue({'packet.ipv4.source', 'packet.upper.dport',
                         'packet.ipv6.proto', 'packet.ether.vlan', 'related',
                         'module.limit'} <= fields)
        self.assertNotIn('in_port', fields)

    def test_rewrite_field_for_renames_only_vlan(self):
        self.assertEqual(translate.rewrite_field_for('packet.ether.vlan'), 'vlan')
        self.assertEqual(translate.rewrite_field_for('in_port'), 'in_port')

    def test_split_port_direction(self):
        self.assertEqual(translate.split_port_direction('r.10_egress'), ('r.10', 'out'))
        self.assertEqual(translate.split_port_direction('r.1_ingress'), ('r.1', 'in'))
        self.assertEqual(translate.split_port_direction('sw.1'), ('sw.1', None))


# --- the rule layer --------------------------------------------------------

class TestRewritesAndForwards(unittest.TestCase):

    def test_rewritten_fields_collects_across_rules_and_tolerates_no_actions(self):
        rules = [
            _rule(actions=[Rewrite([RuleField('packet.ether.vlan', '5')])]),
            _rule(actions=[Rewrite([RuleField('out_port', 'd.2')]), Forward(['d.2'])]),
            _rule(),
        ]
        self.assertEqual(translate.rewritten_fields(rules),
                         {'packet.ether.vlan', 'out_port'})

    def test_forward_ports_are_deduplicated_in_order_and_skip_the_arrival_port(self):
        rule = _rule(actions=[Forward(['d.2', 'd.1']), Rewrite([]), Forward(['d.2', 'd.3'])])
        self.assertEqual(translate._forward_ports(rule), ['d.2', 'd.1', 'd.3'])
        self.assertEqual(translate._forward_ports(rule, 'd.1'), ['d.2', 'd.3'])

    def test_the_three_rewrite_outcomes(self):
        """ All-x is a CLEAR (None), an integer replaces, a prefix is a ternary
        that preserves the unwritten bits, and a port name is its dense id. """
        rule = _rule(actions=[Rewrite([
            RuleField('in_port', 'x' * 32),
            RuleField('out_port', 'd.3'),
            RuleField('packet.ether.vlan', '7'),
            RuleField('packet.ipv4.destination', '10.1.0.0/16'),
        ])])
        self.assertEqual(translate._rewrites(rule, _port_id), [
            ('in_port', None),
            ('out_port', 3),
            ('vlan', 7),
            ('packet.ipv4.destination', 'b' + '0000101000000001' + 'x' * 16),
        ])

    def test_a_fully_determined_bit_vector_rewrite_is_its_integer(self):
        """ `0000000000000101` is VLAN 5 to FaVe's encoder, so it must be 5
        here too, not the decimal 101 `int()` makes of it (TODO item 53). """
        rule = _rule(actions=[Rewrite([
            RuleField('packet.ether.vlan', '0000000000000101')])])
        self.assertEqual(translate._rewrites(rule, _port_id), [('vlan', 5)])

    def test_an_agreeing_duplicate_rewrite_is_collapsed(self):
        rule = _rule(actions=[Rewrite([RuleField('packet.ether.vlan', '7')]),
                              Rewrite([RuleField('packet.ether.vlan', '7')])])
        self.assertEqual(translate._rewrites(rule, _port_id), [('vlan', 7)])

    def test_a_disagreeing_rewrite_is_refused(self):
        rule = _rule(actions=[Rewrite([RuleField('packet.ether.vlan', '7')]),
                              Rewrite([RuleField('packet.ether.vlan', '8')])])
        with self.assertRaises(UnsupportedAction):
            translate._rewrites(rule, _port_id)

    def test_an_unencodable_rewrite_is_refused_as_an_action(self):
        rule = _rule(actions=[Rewrite([RuleField('packet.ether.vlan', 'abc')])])
        with self.assertRaises(UnsupportedAction) as ctx:
            translate._rewrites(rule, _port_id)
        self.assertIn('packet.ether.vlan', str(ctx.exception))


class TestRuleToAd6(unittest.TestCase):

    def test_port_matches_become_fieldmatches_on_dense_ids(self):
        rule = _rule(match=[RuleField('in_port', 'd.1'),
                            RuleField('out_port', 'd.2', negated=True)])
        self.assertEqual(
            _xml(rule_to_ad6(rule, 'k', _target, _port_id)),
            '<rule name="r0" key="k"><fieldmatch field="in_port">1</fieldmatch>'
            '<fieldmatch field="out_port" negated="true">2</fieldmatch></rule>')

    def test_every_forward_port_gets_a_jump_carrying_the_shared_rewrites(self):
        rule = _rule(match=[RuleField('packet.ipv4.destination', '0.0.0.0/0')],
                     actions=[Rewrite([RuleField('packet.ether.vlan', '3')]),
                              Forward(['d.2', 'd.3'])])
        element = rule_to_ad6(rule, 'k', _target, _port_id, position=4)
        self.assertEqual(element.get('name'), 'r4')
        # the match-all destination contributes no condition
        self.assertEqual([child.tag for child in element], ['action', 'action'])
        self.assertEqual([a.get('target') for a in element], ['T_d_2', 'T_d_3'])
        for action in element:
            self.assertEqual(_xml(action[0]), '<rewrite field="vlan" value="3"/>')

    def test_forwarding_only_back_to_the_arrival_port_is_a_drop(self):
        rule = _rule(actions=[Forward(['d.1'])])
        self.assertEqual(len(rule_to_ad6(rule, 'k', _target, _port_id,
                                         arrival_port='d.1')), 0)

    def test_a_miss_action_is_accepted(self):
        self.assertEqual(len(rule_to_ad6(_rule(actions=[Miss()]), 'k',
                                         _target, _port_id)), 0)

    def test_an_unknown_action_kind_is_refused(self):
        class Mirror:     # pylint: disable=too-few-public-methods
            pass
        with self.assertRaises(UnsupportedAction) as ctx:
            rule_to_ad6(_rule(actions=[Mirror()]), 'k1', _target, _port_id)
        self.assertIn('Mirror', str(ctx.exception))
        self.assertIn('k1', str(ctx.exception))


class TestKeys(unittest.TestCase):

    def test_keys_are_dot_and_dash_safe_and_compose(self):
        self.assertEqual(translate.table_key('a.b-c', 'a.b-c.acl'), 'fw_a_b_c_a_b_c_acl')
        self.assertEqual(translate.chain_key('d', 'd.t', None), 'fw_d_d_t')
        self.assertEqual(translate.chain_key('d', 'd.t', 'd.1'), 'fw_d_d_t__d_1')
        self.assertEqual(translate.rule_key('d', 'd.t', 'd.1', 2), 'fw_d_d_t__d_1_r2')
        self.assertEqual(translate.iface_key('a.b', '1_egress'), 'favenet_a_b_1_egress')

    def test_generator_and_probe_entry_keys(self):
        self.assertEqual(translate.generator_entry_key('g'), 'fw_g_g_generator_r0')
        self.assertEqual(translate.probe_entry_key('p'), 'fw_p_p_probe__p_1_r0')


class TestTableToAd6(unittest.TestCase):

    def _names(self, element):
        return [rule.get('key') for rule in element]

    def _dst(self, element):
        return [rule.findtext('ip/address') for rule in element]

    def test_rules_are_emitted_in_ascending_idx(self):
        rules = [_rule(idx=9, match=[RuleField('packet.ipv4.destination', '9.0.0.0/8')]),
                 _rule(idx=1, match=[RuleField('packet.ipv4.destination', '1.0.0.0/8')])]
        element = table_to_ad6('d', 'd.t', 'd.1', rules, _target, _port_id)
        self.assertEqual(element.get('name'), 'd_t__d_1')
        self.assertEqual(self._dst(element), ['1.0.0.0/8', '9.0.0.0/8'])
        self.assertEqual(self._names(element), ['fw_d_d_t__d_1_r0', 'fw_d_d_t__d_1_r1'])

    def test_an_unindexed_table_keeps_its_order(self):
        rules = [_rule(match=[RuleField('packet.ipv4.destination', '9.0.0.0/8')]),
                 _rule(match=[RuleField('packet.ipv4.destination', '1.0.0.0/8')])]
        for rule in rules:
            rule.idx = None
        element = table_to_ad6('d', 'd.t', None, rules, _target, _port_id)
        self.assertEqual(element.get('name'), 'd_t')
        self.assertEqual(self._dst(element), ['9.0.0.0/8', '1.0.0.0/8'])

    def test_a_duplicate_idx_is_refused(self):
        with self.assertRaises(ValueError):
            table_to_ad6('d', 'd.t', None, [_rule(idx=1), _rule(idx=1)],
                         _target, _port_id)

    def test_a_partially_indexed_table_is_refused(self):
        rules = [_rule(idx=1), _rule(idx=2)]
        rules[1].idx = None
        with self.assertRaises(ValueError) as ctx:
            table_to_ad6('d', 'd.t', None, rules, _target, _port_id)
        self.assertIn('mixes', str(ctx.exception))

    def test_a_declared_lpm_table_is_ordered_by_prefix_length(self):
        """ Longest prefix first, ties by idx, a rule with no destination
        (the default) last -- whatever `idx` says. """
        rules = [_rule(idx=0),
                 _rule(idx=1, match=[RuleField('packet.ipv4.destination', '10.0.0.0/8')]),
                 _rule(idx=2, match=[RuleField('packet.ipv4.destination', '10.1.0.0/16')]),
                 _rule(idx=3, match=[RuleField('packet.ipv4.destination', '10.2.0.0/16')])]
        element = table_to_ad6('d', 'd.t', None, rules, _target, _port_id, lpm=True)
        self.assertEqual(self._dst(element),
                         ['10.1.0.0/16', '10.2.0.0/16', '10.0.0.0/8', None])


# --- the port graph --------------------------------------------------------

def _dev(tables, ports=(), wiring=()):
    return {'tables': tables, 'ports': list(ports), 'wiring': list(wiring)}


class TestPortGraphNaming(unittest.TestCase):

    def setUp(self):
        self.graph = PortGraph({
            'a': _dev({}, ports=['1']),
            'a.b': _dev({}, ports=['a.b.2']),
        }, links=[('a.1', 'a.b.2')])

    def test_split_prefers_an_exact_device_then_the_longest_prefix(self):
        self.assertEqual(self.graph.split('a.b.2'), ('a.b', '2'))
        self.assertEqual(self.graph.split('a.b.c.7'), ('a.b', 'c.7'))

    def test_a_port_of_no_declared_device_raises(self):
        with self.assertRaises(KeyError):
            self.graph.split('zz.1')

    def test_target_and_interface_keys(self):
        self.assertEqual(self.graph.target('a.b.2'), 'favenet_a_b_2_out')
        self.assertEqual(self.graph.interface('a.1'), 'favenet_a_1')

    def test_port_ids_are_dense_sorted_and_one_based(self):
        self.assertEqual(self.graph.port_id('a.1'), 1)
        self.assertEqual(self.graph.port_id('a.b.2'), 2)
        self.assertEqual(self.graph.port_id_width(), 2)    # 2 ids need 2 bits

    def test_an_unknown_port_has_no_id(self):
        with self.assertRaises(KeyError):
            self.graph.port_id('a.9')

    def test_ports_of_lists_declared_and_referenced_ports(self):
        self.assertEqual(self.graph.ports_of('a'), ['1'])
        self.assertEqual(self.graph.ports_of('a.b'), ['2'])
        self.assertEqual(self.graph.ports_of('nobody'), [])

    def test_a_link_to_an_undeclared_device_gives_it_no_interface(self):
        """ ports_of skips a port it cannot attribute rather than inventing a
        device for it; resolving such a port as an edge still raises. """
        graph = PortGraph({'a': _dev({}, ports=['1'])}, links=[('a.1', 'ghost.1')])
        self.assertEqual(graph.ports_of('a'), ['1'])
        self.assertEqual(graph.ports_of('ghost'), [])
        with self.assertRaises(KeyError):
            graph.edges()


class TestPortGraphRefusals(unittest.TestCase):

    def test_two_portless_tables_on_one_device_are_refused(self):
        with self.assertRaises(ValueError):
            PortGraph({'d': _dev({'d.x': [_rule()], 'd.y': [_rule()]})})

    def test_an_empty_portless_table_does_not_count(self):
        PortGraph({'d': _dev({'d.x': [_rule()], 'd.empty': []})})

    def test_a_port_entering_two_tables_is_refused(self):
        with self.assertRaises(ValueError):
            PortGraph({'d': _dev({'d.x': [_rule(in_ports=['d.1'])],
                                  'd.y': [_rule(in_ports=['d.1'])]})})

    def test_contradictory_wiring_is_refused_and_duplicates_are_not(self):
        PortGraph({'d': _dev({}, wiring=[('d.1', 'd.2'), ('d.1', 'd.2')])})
        with self.assertRaises(ValueError):
            PortGraph({'d': _dev({}, wiring=[('d.1', 'd.2'), ('d.1', 'd.3')])})

    def test_a_port_reaching_two_tables_through_chains_is_refused_at_entry(self):
        """ The constructor checks only NAMED in_ports. Device `a` names `b.1`
        while `b`'s portless table also receives on it (a link targets it),
        so the port would have two starting points -- refused when resolved. """
        graph = PortGraph({'a': _dev({'a.t': [_rule(in_ports=['b.1'])]}),
                           'b': _dev({'b.t': [_rule()]})},
                          links=[('a.9', 'b.1')])
        with self.assertRaises(ValueError):
            graph.entry('b.1')


class TestPortGraphChainsAndEdges(unittest.TestCase):
    """ One chain per (table, entering port); portless rules join every chain
    and also cover ports the device receives on but no rule names. """

    def setUp(self):
        self.only1 = _rule(idx=0, in_ports=['r.1'], actions=[Forward(['r.3'])])
        self.anyport = _rule(idx=1, actions=[Forward(['r.4'])])
        self.inj = _rule(idx=0, actions=[Forward(['g.1'])])
        self.devices = {
            'r': _dev({'r.t': [self.only1, self.anyport]}, ports=['3', '4'],
                      wiring=[('r.3', 'r.5')]),
            'g': _dev({'g.t': [self.inj]}),
        }
        self.links = [('g.1', 'r.1'), ('g.1', 'r.2'), ('g.1', 'r.1')]
        self.graph = PortGraph(self.devices, self.links)

    def test_chains(self):
        chains = [(d, t, p, [r.idx for r in rules])
                  for d, t, p, rules in self.graph.chains()]
        self.assertEqual(chains, [
            # g's table is entered by nothing: one anonymous chain
            ('g', 'g.t', None, [0]),
            # r.1 is named: it gets the named rule and the portless one
            ('r', 'r.t', 'r.1', [0, 1]),
            # r.2 and r.5 receive (link, wiring) but are named by no rule
            ('r', 'r.t', 'r.2', [1]),
            ('r', 'r.t', 'r.5', [1]),
        ])
        self.assertIs(self.graph.chains(), self.graph.chains())   # memoised

    def test_entry(self):
        self.assertEqual(self.graph.entry('r.2'), 'fw_r_r_t__r_2_r0')
        self.assertIsNone(self.graph.entry('r.3'))

    def test_edges_are_unidirectional_and_deduplicated(self):
        self.assertEqual(self.graph.edges(), [
            ('favenet_r_3_out', 'favenet_r_5_in'),          # wiring
            ('favenet_g_1_out', 'favenet_r_1_in'),          # links, deduped
            ('favenet_g_1_out', 'favenet_r_2_in'),
            ('favenet_r_1_in', 'fw_r_r_t__r_1_r0'),         # arrivals -> entry
            ('favenet_r_2_in', 'fw_r_r_t__r_2_r0'),
            ('favenet_r_5_in', 'fw_r_r_t__r_5_r0'),
        ])

    def test_ports_of_includes_referenced_but_undeclared_ports(self):
        self.assertEqual(self.graph.ports_of('r'), ['1', '2', '3', '4', '5'])
        self.assertEqual(self.graph.ports_of('g'), ['1'])

    def test_a_port_match_value_is_a_port_of_its_device(self):
        graph = PortGraph({'d': _dev({'d.t': [
            _rule(match=[RuleField('out_port', 'd.7')])]})})
        self.assertEqual(graph.ports_of('d'), ['7'])


# --- whole model -----------------------------------------------------------

class TestModelToConfig(unittest.TestCase):

    def setUp(self):
        fib = [_rule(idx=0, node='r', table='r.fib', actions=[Forward(['r.2'])]),
               _rule(idx=1, node='r', table='r.fib',
                     match=[RuleField('packet.ipv4.destination', '10.0.0.0/8')],
                     actions=[Forward(['r.2'])])]
        relabel = [_rule(node='s', table='s.t',
                         match=[RuleField('packet.ether.vlan', '1')],
                         actions=[Rewrite([RuleField('packet.ether.vlan', '2')]),
                                  Forward(['s.2'])])]
        r = _dev({'r.fib': fib})
        r['table_semantics'] = {'r.fib': 'lpm'}
        self.devices = {'r': r, 's': _dev({'s.t': relabel}),
                        'g': translate.generator_device(
                            'g', {'packet.ether.vlan': [RuleField('packet.ether.vlan', '1')]},
                            mutable={'packet.ether.vlan'}),
                        'p': translate.probe_device('p')}
        self.links = [('g.1', 's.1'), ('s.2', 'r.1'), ('r.2', 'p.1')]
        self.config, self.edges = model_to_config(self.devices, self.links)

    def test_one_firewall_and_one_node_per_device_in_sorted_order(self):
        self.assertEqual([fw.get('key') for fw in self.config.iter('{*}firewall')
                          if fw.get('key')],
                         ['fw_g', 'fw_p', 'fw_r', 'fw_s'])
        nodes = list(self.config.iter('{*}node'))
        self.assertEqual([n.get('name') for n in nodes], ['g', 'p', 'r', 's'])
        self.assertEqual([i.get('key') for i in nodes[3].iter('{*}interface')],
                         ['favenet_s_1', 'favenet_s_2'])

    def test_a_declared_lpm_table_puts_the_specific_route_first(self):
        table = next(t for t in self.config.iter('{*}table')
                     if t.get('name') == 'r_fib__r_1')
        self.assertEqual([rule.findtext('{*}ip/{*}address') for rule in table],
                         ['10.0.0.0/8', None])

    def test_the_generators_mutable_constraint_is_a_rewrite_not_a_match(self):
        rule = next(r for r in self.config.iter('{*}rule')
                    if r.get('key') == 'fw_g_g_generator_r0')
        self.assertEqual(rule.findall('{*}fieldmatch'), [])
        rewrites = rule.findall('{*}action/{*}rewrite')
        self.assertEqual([(r.get('field'), r.get('value')) for r in rewrites],
                         [('vlan', '1')])

    def test_edges_link_source_through_to_the_probe(self):
        self.assertIn(('favenet_r_2_out', 'favenet_p_1_in'), self.edges)
        self.assertIn(('favenet_p_1_in', translate.probe_entry_key('p')), self.edges)

    def test_instantiate_base_marks_inits_and_splices_the_edges(self):
        """ Builds the CNF (no solve, so no pycosat): the init node carries the
        INIT proposition and every post-pass edge is a forward transition. """
        from src.xml.xmlutils import XMLUtils
        XMLUtils.deannotate(self.config)
        init = translate.generator_entry_key('g')
        widths = translate.mutable_field_widths({'packet.ether.vlan'})
        kripke, encoding = translate.instantiate_base(
            self.config, self.edges, [init], widths)
        self.assertIn(XMLUtils.INIT, kripke.GetNode(init).Props)
        self.assertEqual(list(kripke.IterInits()), [init])
        for source, target in self.edges:
            self.assertIn((target, True), list(kripke.IterFTransitions(source)))
        self.assertGreater(len(list(encoding.iter())), 1)


class TestWidthsAndVocabulary(unittest.TestCase):

    def test_matched_generic_fields(self):
        rules = [_rule(match=[RuleField('related', '1'),
                              RuleField('module.limit', '900/min'),
                              RuleField('packet.ipv4.source', '1.2.3.4')])]
        self.assertEqual(translate.matched_generic_fields(rules),
                         {'related', 'module.limit'})

    def test_mutable_field_widths_per_kind(self):
        self.assertEqual(
            translate.mutable_field_widths(
                {'packet.ether.vlan', 'in_port', 'module.limit',
                 'packet.ipv4.destination', 'related'},
                port_width=3, matched={'related', 'module.ipv6header.header'}),
            {'vlan': 12, 'in_port': 3, 'module.limit': 32,
             'packet.ipv4.destination': 32, 'related': 8,
             'module.ipv6header.header': 8})

    def test_a_port_field_needs_the_graphs_width(self):
        with self.assertRaises(UnsupportedField):
            translate.mutable_field_widths({'out_port'})

    def test_a_rewritten_field_with_no_declared_width_is_refused(self):
        with self.assertRaises(UnsupportedField):
            translate.mutable_field_widths({'packet.upper.dport'})

    def test_a_matched_field_with_no_declared_width_is_refused(self):
        with self.assertRaises(UnsupportedField):
            translate.mutable_field_widths((), matched={'packet.upper.dport'})

    def test_constrained_fields_spans_matches_and_rewrites(self):
        rules = [_rule(match=[RuleField('related', '1')],
                       actions=[Rewrite([RuleField('in_port', 'd.1')])])]
        self.assertEqual(translate.constrained_fields(rules), {'related', 'in_port'})


class TestGeneratorsAndProbes(unittest.TestCase):

    def test_a_multi_valued_generator_field_is_refused(self):
        with self.assertRaises(UnsupportedField) as ctx:
            translate.generator_device('g', {'packet.ipv4.source': [
                RuleField('packet.ipv4.source', '1.0.0.0/8'),
                RuleField('packet.ipv4.source', '2.0.0.0/8')]})
        self.assertIn('DISJUNCTION', str(ctx.exception))

    def test_an_immutable_generator_field_is_a_match(self):
        device = translate.generator_device(
            'g', {'packet.ipv4.source': [RuleField('packet.ipv4.source', '1.0.0.0/8')],
                  'packet.upper.dport': []}, port='7')
        (rule,) = device['tables']['g.generator']
        self.assertEqual(rule.in_ports, [])
        self.assertEqual([f.name for f in rule.match], ['packet.ipv4.source'])
        self.assertEqual([type(a).__name__ for a in rule.actions], ['Forward'])
        self.assertEqual(rule.actions[0].ports, ['g.7'])
        self.assertEqual(device['ports'], ['7'])

    def test_a_probe_terminates_on_its_own_port(self):
        device = translate.probe_device('p', port='3')
        (rule,) = device['tables']['p.probe']
        self.assertEqual(rule.in_ports, ['p.3'])
        self.assertEqual((list(rule.match), rule.actions), ([], []))


class TestQueryFieldRecipes(unittest.TestCase):
    """ The bridge forces a query condition into whichever namespace the
    translator used; every constrained field gets an entry. """

    def test_every_branch(self):
        rules = [_rule(
            match=[RuleField('packet.upper.dport', '22'),
                   RuleField('packet.ipv6.proto', 'tcp'),
                   RuleField('packet.ipv4.source', '1.0.0.0/8'),
                   RuleField('packet.ipv4.destination', '2.0.0.0/8'),
                   RuleField('related', '1'),
                   RuleField('packet.upper.tcp.flags', '1xxxxxxx'),
                   RuleField('in_port', 'd.1')],
            actions=[Rewrite([RuleField('packet.ipv4.destination', '3.0.0.0/8')])])]
        recipes = translate.query_field_recipes(
            rules, mutable={'packet.ipv4.destination'}, port_width=4)
        self.assertEqual(recipes['in_port'],
                         {'scope': 'node', 'field': 'in_port', 'width': 4})
        self.assertEqual(recipes['packet.ipv4.destination'],
                         {'scope': 'node', 'field': 'packet.ipv4.destination',
                          'width': 32})
        self.assertEqual(recipes['related'],
                         {'scope': 'node', 'field': 'related', 'width': 8})
        self.assertEqual(recipes['packet.upper.dport'],
                         {'scope': 'global', 'kind': 'port', 'direction': 'dst'})
        self.assertEqual(recipes['packet.ipv6.proto']['names']['6'], 'tcp')
        self.assertEqual(recipes['packet.ipv4.source'],
                         {'scope': 'global', 'kind': 'cidr', 'direction': 'src',
                          'version': '4'})
        self.assertEqual(recipes['packet.upper.tcp.flags']['scope'], 'unsupported')
        self.assertEqual(len(recipes), 7)

    def test_an_unconstrained_model_has_no_recipes(self):
        self.assertEqual(translate.query_field_recipes([_rule()]), {})


if __name__ == '__main__':
    unittest.main()
