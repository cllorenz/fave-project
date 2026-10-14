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

""" The device-model base classes, built by hand: AbstractDeviceModel (table
semantics, the LPM validation, the add/delete buffers, JSON, diff), and the
firewall family on top of it -- AbstractFirewallModel's address binding, route
expansion and removal, the application-layer gateway's relay and the snapshot
packet filter's state commands. Pure Python, no parser, no backend.

test_devices.py covers wiring invariants and the route split; this file covers
the rest of each class's contract.
"""

import json
import unittest

from devices.abstract_device import (
    AbstractDeviceModel, TableSemanticsError, FIRST_MATCH, LPM,
    lpm_prefix_len, validate_lpm_rules, restore_table_semantics,
)
from devices.abstract_firewall import AbstractFirewallModel
from devices.application_layer_gateway import (
    ApplicationLayerGatewayModel, RelayCommand,
)
from devices.packet_filter import PacketFilterModel
from devices.snapshot_packet_filter import (
    SnapshotPacketFilterModel, StateCommand,
)
from devices.switch import SwitchModel
from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from topology.topology import TopologyCommand


def _route(idx, dst=None, ports=None, extra=None, negated=False):
    """ A routing-table rule on node 'n' matching `dst` (and `extra`). """
    fields = []
    if dst is not None:
        name = 'packet.ipv6.destination' if ':' in dst else 'packet.ipv4.destination'
        fields.append(RuleField(name, dst, negated=negated))
    fields.extend(extra or [])
    return Rule('n', 'n.routing', idx, match=Match(fields),
                actions=[Forward(ports)] if ports is not None else [])


def _fields(rule):
    return [(f.name, f.value) for f in rule.match]


class TestLpmPrefixLen(unittest.TestCase):
    """ The destination prefix length a rule matches; -1 without one. """

    def test_prefix_lengths(self):
        self.assertEqual(lpm_prefix_len(_route(0, '10.0.0.0/8')), 8)
        self.assertEqual(lpm_prefix_len(_route(0, '10.0.0.1')), 32)
        self.assertEqual(lpm_prefix_len(_route(0, '2001:db8::1')), 128)
        self.assertEqual(lpm_prefix_len(_route(0, '2001:db8::/32')), 32)
        self.assertEqual(lpm_prefix_len(_route(0)), -1)


class TestValidateLpmRules(unittest.TestCase):
    """ A table declared LPM must match destination prefixes only, none of
    them negated, and no prefix may carry two different actions. """

    def test_a_proper_fib_passes(self):
        validate_lpm_rules('n', 'n.routing', [
            _route(0, '10.0.0.0/8', ['a']),
            _route(1, '10.1.0.0/16', ['b']),
            _route(2, None, ['c']),
            _route(3, '10.0.0.0/8', ['a']),     # a duplicate that agrees
        ])

    def test_a_negated_destination_is_refused(self):
        with self.assertRaisesRegex(TableSemanticsError, 'NEGATED'):
            validate_lpm_rules('n', 'n.routing',
                               [_route(4, '10.0.0.0/8', ['a'], negated=True)])

    def test_another_matched_field_is_refused(self):
        rule = _route(5, '10.0.0.0/8', ['a'],
                      extra=[RuleField('packet.upper.dport', '80')])
        with self.assertRaisesRegex(TableSemanticsError,
                                    'rule 5 also matches packet.upper.dport'):
            validate_lpm_rules('n', 'n.routing', [rule])

    def test_two_actions_on_one_prefix_are_ambiguous(self):
        with self.assertRaisesRegex(TableSemanticsError, 'two rules match 10.0.0.0/8'):
            validate_lpm_rules('n', 'n.routing', [
                _route(0, '10.0.0.0/8', ['a']), _route(1, '10.0.0.0/8', [])])

    def test_two_default_routes_collide_across_batches(self):
        seen = {}
        validate_lpm_rules('n', 'n.routing', [_route(0, None, ['a'])], seen=seen)
        with self.assertRaisesRegex(TableSemanticsError, 'the default route'):
            validate_lpm_rules('n', 'n.routing', [_route(1, None, ['b'])], seen=seen)


class _DroppingModel(AbstractDeviceModel):
    """ A model whose to_json does NOT chain to the base, so it cannot carry a
    table-semantics declaration. """

    def to_json(self):
        return {'node': self.node, 'type': self.type}


class TestTableSemantics(unittest.TestCase):
    """ Declarations are overrides only, validated on the way in, and refused
    by a model that would lose them on serialisation. """

    def test_default_is_first_match_and_not_serialised(self):
        model = AbstractDeviceModel('n', tables={'n.1': []})
        self.assertEqual(model.semantics_of('n.1'), FIRST_MATCH)
        self.assertNotIn('table_semantics', model.to_json())

    def test_declaring_and_undeclaring_lpm(self):
        model = AbstractDeviceModel('n', tables={'n.1': []})
        model.set_table_semantics('n.1', LPM)
        self.assertEqual(model.semantics_of('n.1'), LPM)
        self.assertEqual(model.to_json()['table_semantics'], {'n.1': LPM})
        model.set_table_semantics('n.1', FIRST_MATCH)
        self.assertEqual(model.table_semantics, {})

    def test_an_unknown_term_is_refused(self):
        model = AbstractDeviceModel('n')
        with self.assertRaisesRegex(TableSemanticsError, "unknown table semantics 'fib'"):
            model.set_table_semantics('n.1', 'fib')

    def test_a_model_that_would_drop_it_refuses_and_keeps_nothing(self):
        model = _DroppingModel('n')
        with self.assertRaisesRegex(TableSemanticsError, 'does not carry table_semantics'):
            model.set_table_semantics('n.1', LPM)
        self.assertEqual(model.table_semantics, {})


class TestRestoreTableSemantics(unittest.TestCase):
    """ Declarations are read back off a serialised model, including one
    wrapped in a topology command; reading is tolerant. """

    def test_a_non_dict_is_returned_untouched(self):
        model = SwitchModel('sw')
        self.assertIs(restore_table_semantics(model, 'not json'), model)

    def test_a_wrapped_model_gets_its_declaration_back(self):
        switch = SwitchModel('sw', ports=['1'])
        switch.set_table_semantics('sw.1', LPM)
        wire = TopologyCommand('sw', 'add', model=switch).to_json()

        cmd = TopologyCommand.from_json(json.loads(json.dumps(wire)))
        self.assertEqual(cmd.model.table_semantics, {},
                         "from_json alone does not restore declarations")
        self.assertIs(restore_table_semantics(cmd, wire), cmd)
        self.assertEqual(cmd.model.table_semantics, {'sw.1': LPM})


class TestAbstractDeviceModel(unittest.TestCase):
    """ Buffers, indices, JSON and the diff of the base model. """

    def setUp(self):
        self.rule = Rule('n', 'n.a', 1, match=Match([RuleField('packet.upper.dport', '80')]),
                         actions=[Forward(['n.2'])])
        self.model = AbstractDeviceModel(
            'n', 'model', tables={'n.b': [], 'n.a': [self.rule]},
            ports={'n.2': 'n.a', 'n.1': 'n.a'}, wiring=[('n.1', 'n.2')])

    def test_identity_ports_and_sorted_indices(self):
        self.assertEqual(self.model.ingress_port('n.1'), 'n.1')
        self.assertEqual(self.model.egress_port('n.1'), 'n.1')
        self.assertEqual(self.model.table_index('n.b'), 1)
        self.assertEqual(self.model.port_index('n.1'), 0)
        self.assertIn('node: n', str(self.model))

    def test_buffers_and_reset(self):
        self.model.add_rule(self.rule)
        self.model.remove_rule(7)
        self.assertEqual(self.model._adds['n.a'], [self.rule])
        self.assertEqual(self.model._deletes, [7])
        self.model.reset()
        self.assertEqual(self.model._adds, {'n.a': [], 'n.b': []})
        self.assertEqual(self.model._deletes, [])

    def test_json_string_round_trip(self):
        back = AbstractDeviceModel.from_string(self.model.to_json_str())
        self.assertEqual(back.node, 'n')
        self.assertEqual(back.wiring, [('n.1', 'n.2')])
        self.assertEqual(back.ports, self.model.ports)
        # tables come back as their JSON, not as Rule objects
        self.assertEqual(back.tables['n.a'], [self.rule.to_json()])

    def test_diff_keeps_only_what_the_other_lacks(self):
        other = AbstractDeviceModel('n', 'model', tables={'n.a': [], 'n.b': []},
                                    ports={'n.1': 'n.a'}, wiring=[])
        diff = self.model - other
        self.assertEqual(diff.tables, {'n.a': [self.rule]})
        self.assertEqual(diff.ports, {'n.2': 'n.a'})
        self.assertEqual(diff.wiring, [('n.1', 'n.2')])
        self.assertEqual((self.model - self.model).tables, {})

    def test_equality(self):
        same = AbstractDeviceModel(
            'n', 'model', tables={'n.b': [], 'n.a': [self.rule]},
            ports={'n.2': 'n.a', 'n.1': 'n.a'}, wiring=[('n.1', 'n.2')])
        self.assertEqual(self.model, same)
        self.assertFalse(self.model != same)
        same.wiring = []
        self.assertNotEqual(self.model, same)
        self.assertNotEqual(self.model, 'n')


class TestAbstractFirewall(unittest.TestCase):
    """ The firewall base: port naming, address binding, routes. """

    def setUp(self):
        self.fw = PacketFilterModel('fw', ports=['1', '2'])

    def test_internal_ports_keep_their_name(self):
        self.assertEqual(self.fw.ingress_port('fw.1'), 'fw.1_ingress')
        self.assertEqual(self.fw.egress_port('fw.1'), 'fw.1_egress')
        internal = next(iter(self.fw.internal_ports))
        self.assertEqual(self.fw.ingress_port(internal), internal)
        self.assertEqual(self.fw.egress_port(internal), internal)

    def test_default_ports(self):
        self.assertEqual(sorted(AbstractFirewallModel('x', 'packet_filter').ports),
                         ['x.1', 'x.2'])

    def test_ipv4_address_binds_local_delivery_then_forwarding(self):
        self.fw.set_address('192.0.2.1')
        pre = self.fw.tables['fw.pre_routing']
        local = [r for r in pre if r.match]
        rest = [r for r in pre if not r.match]
        self.assertEqual(len(local), 2)
        self.assertEqual(len(rest), 2)
        self.assertEqual({_fields(r)[0] for r in local},
                         {('packet.ipv4.destination', '192.0.2.1')})
        self.assertEqual({r.actions[1].ports[0] for r in local},
                         {'fw.pre_routing_input'})
        self.assertEqual({r.actions[1].ports[0] for r in rest},
                         {'fw.pre_routing_forward'})
        self.assertTrue(max(r.idx for r in local) < min(r.idx for r in rest))
        for rule in pre:
            self.assertEqual(rule.actions[0], Rewrite([RuleField('in_port', rule.in_ports[0])]))

    def test_ipv6_address(self):
        self.fw.set_address('2001:db8::1')
        self.assertIn(('packet.ipv6.destination', '2001:db8::1'),
                      _fields(self.fw.tables['fw.pre_routing'][0]))

    def test_egress_port_spellings_are_normalised(self):
        for given in ['fw.2_egress', 'fw.2', '2']:
            with self.subTest(given=given):
                fw = PacketFilterModel('fw', ports=['1', '2'])
                fw.add_rules([Rule('fw', 'fw.routing', 1, actions=[Forward([given])])])
                keep = fw._adds['fw.routing'][0]
                self.assertIn(('out_port', 'fw.2_egress'), _fields(keep))

    def test_a_route_to_two_ports_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'forwards to 2 ports'):
            self.fw.add_rules([Rule('fw', 'fw.routing', 1, actions=[Forward(['1', '2'])])])

    def test_remove_and_update_a_route(self):
        dst = RuleField('packet.ipv6.destination', '2001:db8::/32')
        self.fw.tables['fw.routing'] = [
            Rule('fw', 'fw.routing', i, match=Match([dst])) for i in (2, 3, 4)]
        self.fw.remove_rule(1)
        self.assertEqual(self.fw._deletes, [2, 3])
        self.assertEqual([r.idx for r in self.fw.tables['fw.routing']], [4])

        new = Rule('fw', 'fw.routing', 99, match=Match([dst]), actions=[Forward(['1'])])
        self.fw.update_rule(2, new)
        self.assertEqual(self.fw._deletes, [2, 3, 4, 5])
        self.assertEqual(sorted(r.idx for r in self.fw._adds['fw.routing']), [4, 5])

    def test_diff_is_the_add_buffer(self):
        self.fw.add_rules([Rule('fw', 'fw.routing', 1, actions=[])])
        diff = self.fw - PacketFilterModel('fw', ports=['1', '2'])
        self.assertIsInstance(diff, AbstractFirewallModel)
        self.assertEqual([r.idx for r in diff.tables['fw.routing']], [3])
        self.assertEqual(diff.type, 'packet_filter')


class TestApplicationLayerGateway(unittest.TestCase):
    """ The relay table, the relay command and an address at construction. """

    def test_relay_rules_are_bound_into_the_relay_table(self):
        alg = ApplicationLayerGatewayModel('alg', ports=['1', '2'])
        rule = Rule('alg', 'x', 1, in_ports=['elsewhere'],
                    actions=[Forward(['somewhere']), Forward([])])
        alg.add_relay([rule])
        self.assertEqual(alg._adds['alg.relay'], [rule])
        self.assertEqual(rule.tid, 'alg.relay')
        self.assertEqual(rule.in_ports, ['alg.relay_in'])
        self.assertEqual([a.ports for a in rule.actions], [['alg.relay_out'], []])

    def test_address_binds_pre_routing(self):
        alg = ApplicationLayerGatewayModel('alg', address='2001:db8::1')
        self.assertTrue(any(('packet.ipv6.destination', '2001:db8::1') in _fields(r)
                            for r in alg.tables['alg.pre_routing']))

    def test_relay_command_round_trip(self):
        rule = Rule('alg', 'alg.relay', 1, match=Match([RuleField('packet.upper.dport', '25')]),
                    actions=[Forward(['alg.relay_out'])])
        cmd = RelayCommand('alg', 'add', [rule])
        j = cmd.to_json()
        self.assertEqual((j['type'], j['command']), ('relay_command', 'add'))
        back = RelayCommand.from_json(json.dumps(j))
        self.assertEqual(back.to_json(), j)
        self.assertEqual(back.rules, [rule])


class TestSnapshotPacketFilter(unittest.TestCase):
    """ The snapshot packet filter's JSON, address and state command. """

    def test_state_tables_default_to_a_miss(self):
        spf = SnapshotPacketFilterModel('s', address='192.0.2.1')
        for table in ('s.input_state', 's.forward_state', 's.output_state'):
            [miss] = spf.tables[table]
            self.assertEqual((miss.idx, miss.actions), (65535, [Forward([table + '_miss'])]))
        self.assertIn(('packet.ipv4.destination', '192.0.2.1'),
                      _fields(spf.tables['s.pre_routing'][0]))

    def test_json_round_trip(self):
        spf = SnapshotPacketFilterModel('s', ports=['1', '2', '3'])
        back = SnapshotPacketFilterModel.from_json(json.dumps(spf.to_json()))
        self.assertEqual(back.to_json(), spf.to_json())
        self.assertEqual(back, spf)

    def test_state_command_round_trip(self):
        rule = Rule('s', 's.forward_state', 1,
                    match=Match([RuleField('packet.ipv6.source', '2001:db8::1')]),
                    actions=[Forward(['s.forward_state_accept'])])
        cmd = StateCommand('s', 'add_state', [rule])
        j = cmd.to_json()
        self.assertEqual(j['type'], 'state_command')
        back = StateCommand.from_json(json.dumps(j))
        self.assertEqual((back.node, back.command), ('s', 'add_state'))
        self.assertEqual(back.rules, [rule])


if __name__ == '__main__':
    unittest.main()
