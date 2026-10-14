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

""" topology/topology.py in the fast tier: the link/generator collection models,
TopologyCommand's JSON round trip for every model type, the CLI's argument
parsers, and `main()` end to end -- with the aggregator connection mocked, so
what is pinned is the exact message `main()` would put on the wire.

test_topology.py (integration tier) covers the links model too; it sits there
only because it is listed beside the pybison tests. The packet-filter types of
`main()` normally parse an ip6tables file through PyBison; here the lazy parser
is replaced by a stub that returns a hand-built AST, so the generator path runs
without `bison`.
"""

import json
import os
import tempfile
import unittest

from types import SimpleNamespace
from unittest import mock

import topology.topology as topo

from devices.abstract_device import TableSemanticsError
from devices.application_layer_gateway import ApplicationLayerGatewayModel
from devices.generator import GeneratorModel
from devices.packet_filter import PacketFilterModel
from devices.probe import ProbeModel
from devices.router import RouterModel
from devices.snapshot_packet_filter import SnapshotPacketFilterModel
from devices.switch import SwitchModel
from rule.rule_model import RuleField
from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
from util.tree_util import Tree

from topology.topology import (
    LinksModel, GeneratorsModel, TopologyCommand,
    _parse_links, _parse_fields, _parse_probe_fields, _parse_ports,
    _parse_generators,
)


def _build(tpls):
    """ A Tree from nested tuples; the first element is the node value. """
    if not isinstance(tpls, tuple):
        return Tree(tpls)
    tree = _build(tpls[0])
    for child in tpls[1:]:
        tree.add_child(_build(child))
    return tree


def _forward_ruleset():
    """ The AST of `-P FORWARD DROP` and one `-A FORWARD -d ... -j ACCEPT`. """
    ast = Tree('root')
    for lineno, (raw, body) in enumerate([
            ('ip6tables -P FORWARD DROP', ('-P', ('FORWARD', ('DROP',)))),
            ('ip6tables -A FORWARD -d 2001:db8::1 -j ACCEPT',
             ('-A', ('FORWARD',), ('-d', ('2001:db8::1',)), ('-j', ('ACCEPT',)))),
    ]):
        ast.add_child(_build(
            (raw, body, ('-t', ('filter',)), ('--line-no', (str(lineno),)))
        ))
    return ast


class _MainHarness(unittest.TestCase):
    """ Runs `topology.main` with the aggregator connection mocked out; every
    message it sends is decoded into `self.sent`. """

    def setUp(self):
        self.sent = []
        self.conn = mock.MagicMock(name='conn')
        patches = [
            mock.patch.object(topo, 'connect_to_fave', return_value=self.conn),
            mock.patch.object(
                topo, 'fave_sendmsg',
                side_effect=lambda _c, data: self.sent.append(json.loads(data))
            ),
        ]
        self.connect = patches[0].start()
        for patch in patches[1:]:
            patch.start()
        for patch in patches:
            self.addCleanup(patch.stop)

    def run_main(self, argv):
        """ One `main()` call; returns the single message it sent. """
        before = len(self.sent)
        topo.main(argv)
        self.assertEqual(len(self.sent), before + 1, "main sends exactly one message")
        self.conn.close.assert_called()
        return self.sent[-1]


class TestLinksModel(unittest.TestCase):
    """ A links model groups its triples by source port in JSON and iterates
    them back as triples. """

    def test_json_round_trip_and_iteration(self):
        links = LinksModel([('a.1', 'b.1', False), ('a.1', 'c.1', True)])
        j = links.to_json()
        self.assertEqual(j, {'type': 'links',
                             'links': {'a.1': [('b.1', False), ('c.1', True)]}})
        again = LinksModel.from_json(json.dumps(j))
        self.assertEqual(again, links)
        self.assertEqual(list(again), [('a.1', 'b.1', False), ('a.1', 'c.1', True)])

    def test_equality_needs_the_same_links(self):
        self.assertNotEqual(LinksModel([('a.1', 'b.1', False)]),
                            LinksModel([('a.1', 'b.1', True)]))


class TestGeneratorsModel(unittest.TestCase):
    """ The bulk generators model serialises each generator and compares as an
    unordered collection. """

    def _gens(self):
        return [
            GeneratorModel('g1', {'ipv6_src': [RuleField('ipv6_src', '2001:db8::1')]}),
            GeneratorModel('g2'),
        ]

    def test_json_round_trip(self):
        model = GeneratorsModel(self._gens())
        j = model.to_json()
        self.assertEqual(j['type'], 'generators')
        self.assertEqual([g['node'] for g in j['generators']], ['g1', 'g2'])
        # Compared as JSON: GeneratorModel defines no __eq__, so two equal
        # generators that are distinct objects do not compare equal.
        self.assertEqual(GeneratorsModel.from_json(json.dumps(j)).to_json(), j)
        self.assertEqual([g.node for g in model], ['g1', 'g2'])

    def test_equality_ignores_order_but_not_membership(self):
        # Same generator OBJECTS throughout (see test_json_round_trip).
        one, two = self._gens()
        self.assertEqual(GeneratorsModel([one, two]), GeneratorsModel([two, one]))
        self.assertNotEqual(GeneratorsModel([one]), GeneratorsModel([two]))


class TestTopologyCommandJson(unittest.TestCase):
    """ `TopologyCommand.from_json` rebuilds the model class named by the
    model's own type, for every type the aggregator accepts. """

    def _round_trip(self, model):
        cmd = TopologyCommand(model.node if hasattr(model, 'node') else 'x', 'add',
                              model=model)
        self.assertEqual(cmd.mtype, model.type)
        back = TopologyCommand.from_json(json.dumps(cmd.to_json()))
        self.assertIsInstance(back.model, type(model))
        self.assertEqual(back.mtype, model.type)
        self.assertEqual(back.to_json(), cmd.to_json())
        return back

    def test_every_model_type_round_trips(self):
        for model in [
                SwitchModel('sw', ports=['1', '2']),
                PacketFilterModel('pf', ports=['1', '2']),
                SnapshotPacketFilterModel('spf', ports=['1', '2']),
                RouterModel('r', ports=['1', '2']),
                GeneratorModel('g'),
                ProbeModel('p', 'universal'),
                LinksModel([('a.1', 'b.1', False)]),
                GeneratorsModel([GeneratorModel('g')]),
        ]:
            with self.subTest(mtype=model.type):
                self._round_trip(model)

    def test_application_layer_gateway_round_trips(self):
        self._round_trip(ApplicationLayerGatewayModel('alg', ports=['1', '2']))

    def test_a_delete_carries_no_model_but_keeps_its_mtype(self):
        cmd = TopologyCommand('sw', 'del', mtype='switch')
        j = cmd.to_json()
        self.assertEqual(j, {'node': 'sw', 'type': 'topology_command',
                             'command': 'del', 'mtype': 'switch'})
        back = TopologyCommand.from_json(j)
        self.assertIsNone(back.model)
        self.assertEqual(back.mtype, 'switch')
        self.assertEqual(back, cmd)

    def test_without_mtype_the_field_is_omitted(self):
        self.assertNotIn('mtype', TopologyCommand('sw', 'del').to_json())
        self.assertEqual(TopologyCommand.from_json(
            {'node': 'sw', 'command': 'del'}).mtype, '')


class TestArgumentParsers(unittest.TestCase):
    """ The per-option parsers of the CLI. """

    def test_links(self):
        self.assertEqual(_parse_links('a.1:b.1:True,b.2:c.1:False'),
                         [('a.1', 'b.1', True), ('b.2', 'c.1', False)])

    def test_fields_add_the_protocol_of_a_port_field(self):
        self.assertEqual(
            _parse_fields('ipv6_dst=2001:db8::1,2001:db8::2;tcp_dst=80'),
            {'ipv6_dst': ['2001:db8::1', '2001:db8::2'], 'tcp_dst': ['80'],
             'ip_proto': ['tcp']})
        self.assertEqual(_parse_fields('udp_src=53')['ip_proto'], ['udp'])
        self.assertEqual(_parse_fields('icmpv6_type=128')['ip_proto'], ['icmp'])
        self.assertNotIn('ip_proto', _parse_fields('vlan=10'))

    def test_probe_fields_become_rule_fields(self):
        fields = _parse_probe_fields('in_port=a,b;vlan=3')
        self.assertEqual(sorted(fields), ['in_port', 'vlan'])
        self.assertEqual([(f.name, f.value) for f in fields['in_port']],
                         [('in_port', 'a'), ('in_port', 'b')])

    def test_ports_as_a_count_or_a_literal_list(self):
        self.assertEqual(_parse_ports('3'), [1, 2, 3])
        self.assertEqual(_parse_ports('[1, 4]'), ['1', '4'])
        self.assertEqual(_parse_ports('1,4'), ['1', '4'])

    def test_generators(self):
        gens = _parse_generators('g1\\ipv6_src=2001:db8::1,2001:db8::2|g2\\')
        self.assertEqual([name for name, _f in gens], ['g1', 'g2'])
        self.assertEqual([f.value for f in gens[0][1]['ipv6_src']],
                         ['2001:db8::1', '2001:db8::2'])
        self.assertEqual(gens[1][1], {})


class TestMainSendsOneCommand(_MainHarness):
    """ `main()` builds the model its options describe and sends it as ONE
    TopologyCommand to the default aggregator address. """

    def test_add_switch_with_table_ids_and_semantics(self):
        msg = self.run_main(['-a', '-t', 'switch', '-n', 'sw', '-p', '2',
                             '-I', "{'sw.1': 1}", '-S', "{'sw.1': 'lpm'}"])
        self.connect.assert_called_with(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
        self.assertEqual(msg['type'], 'topology_command')
        self.assertEqual((msg['node'], msg['command'], msg['mtype']),
                         ('sw', 'add', 'switch'))
        self.assertEqual(msg['model']['ports'], {'sw.1': 'sw.1', 'sw.2': 'sw.1'})
        self.assertEqual(msg['model']['table_ids'], {'sw.1': 1})
        self.assertEqual(msg['model']['table_semantics'], {'sw.1': 'lpm'})

    def test_an_unknown_table_semantics_is_refused_before_sending(self):
        with self.assertRaises(TableSemanticsError):
            topo.main(['-t', 'switch', '-n', 'sw', '-p', '1',
                       '-S', "{'sw.1': 'longest'}"])
        self.assertEqual(self.sent, [])

    def test_links_imply_the_links_type(self):
        msg = self.run_main(['-l', 'a.1:b.1:True,b.2:c.1:False'])
        self.assertEqual(msg['mtype'], 'links')
        self.assertEqual(msg['model']['links'],
                         {'a.1': [['b.1', True]], 'b.2': [['c.1', False]]})

    def test_delete_links(self):
        msg = self.run_main(['-d', '-l', 'a.1:b.1:False'])
        self.assertEqual((msg['node'], msg['command']), ('links', 'del'))
        self.assertEqual(msg['model']['links'], {'a.1': [['b.1', False]]})

    def test_delete_a_device_over_the_unix_socket(self):
        msg = self.run_main(['-d', '-n', 'sw', '-u'])
        self.connect.assert_called_with(FAVE_DEFAULT_UNIX)
        self.assertEqual(msg, {'node': 'sw', 'type': 'topology_command',
                               'command': 'del'})

    def test_ports_imply_add(self):
        msg = self.run_main(['-d', '-t', 'switch', '-n', 'sw', '-p', '1'])
        self.assertEqual(msg['command'], 'add')

    def test_add_generator_maps_field_names(self):
        msg = self.run_main(['-t', 'generator', '-n', 'g',
                             '-f', 'ipv6_dst=2001:db8::1;tcp_dst=80'])
        fields = msg['model']['fields']
        self.assertEqual(sorted(fields), ['packet.ipv6.destination',
                                          'packet.ipv6.proto', 'packet.upper.dport'])
        self.assertEqual(fields['packet.ipv6.proto'][0]['value'], '6')

    def test_add_generators_in_bulk(self):
        msg = self.run_main(['-t', 'generators', '-G',
                             'g1\\ipv6_src=2001:db8::1|g2\\'])
        self.assertEqual(msg['mtype'], 'generators')
        self.assertEqual([g['node'] for g in msg['model']['generators']], ['g1', 'g2'])
        self.assertEqual(msg['model']['generators'][1]['fields'], {})

    def test_add_probe(self):
        msg = self.run_main(['-t', 'probe', '-n', 'p', '-q', 'existential',
                             '-F', 'in_port=x', '-T', 'tcp_dst=80',
                             '-P', '.*(port=sw.1);(port in (sw.2))'])
        model = msg['model']
        self.assertEqual((model['type'], model['quantor']), ('probe', 'existential'))
        self.assertEqual(model['match'], {'fields': []})
        self.assertEqual(list(model['test_fields']), ['packet.upper.dport'])
        self.assertEqual(model['test_path']['pathlets'],
                         [{'type': 'port', 'port': 'sw.1'},
                          {'type': 'next_ports', 'ports': ['sw.2']}])

    def test_add_router_from_a_cisco_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = os.path.join(tmp, 'router.conf')
            with open(conf, 'w', encoding='utf-8') as out:
                out.write(
                    "access-list 10 permit ip 10.0.1.0 0.0.0.255 10.0.2.0 0.0.0.255\n"
                    "interface Vlan 2\n"
                    " ip access-group 10 in\n"
                )
            msg = self.run_main(['-t', 'router', '-n', 'r', '-p', '1,2', '-r', conf])
        model = msg['model']
        self.assertEqual(model['type'], 'router')
        acl_in = model['tables']['r.acl_in']
        self.assertEqual(
            [f['value'] for f in acl_in[-1]['match']['fields']],
            ['2', '10.0.1.0/24', '10.0.2.0/24'])
        self.assertEqual(model['table_semantics'], {'r.routing': 'lpm'})


class TestMainPacketFilters(_MainHarness):
    """ The ip6tables-backed types, with the PyBison parser replaced by a stub
    returning a hand-built AST: the parser is handed `-r`, and the generated
    model's type follows the `-t` given. """

    def setUp(self):
        super().setUp()
        self.parsed = []

        def parse(path):
            self.parsed.append(path)
            return _forward_ruleset()

        patch = mock.patch.object(topo, 'IP6TABLES_PARSER', SimpleNamespace(parse=parse))
        patch.start()
        self.addCleanup(patch.stop)

    def _forward_rules(self, msg):
        return msg['model']['tables'][msg['node'] + '.forward_filter']

    def test_packet_filter(self):
        msg = self.run_main(['-t', 'packet_filter', '-n', 'pf', '-i', '2001:db8::fe',
                             '-p', '2', '-r', 'rules.txt'])
        self.assertEqual(self.parsed, ['rules.txt'])
        self.assertEqual(msg['mtype'], 'packet_filter')
        rules = self._forward_rules(msg)
        self.assertEqual(len(rules), 2)
        self.assertIn('packet.ipv6.destination',
                      [f['name'] for r in rules for f in (r['match'] or {}).get('fields', [])])
        # the address is bound in pre_routing
        self.assertTrue(any(
            f['value'] == '2001:db8::fe'
            for r in msg['model']['tables']['pf.pre_routing']
            for f in (r['match'] or {}).get('fields', [])))

    def test_application_layer_gateway_option_parses_the_ruleset(self):
        # Only that the ruleset is parsed and its rules generated: which model
        # type this option SHOULD yield is not pinned (today the generator,
        # which builds packet filters only, returns a plain packet filter).
        msg = self.run_main(['-t', 'application_layer_gateway', '-n', 'alg',
                             '-p', '2', '-r', 'rules.txt', '-s'])
        self.assertEqual(self.parsed, ['rules.txt'])
        self.assertEqual(len(self._forward_rules(msg)), 2)

    def test_snapshot_packet_filter(self):
        msg = self.run_main(['-t', 'snapshot_packet_filter', '-n', 'spf',
                             '-p', '2', '-r', 'rules.txt'])
        self.assertEqual(msg['mtype'], 'snapshot_packet_filter')
        self.assertIn('spf.forward_state', msg['model']['tables'])
        self.assertEqual(len(self._forward_rules(msg)), 2)


if __name__ == '__main__':
    unittest.main()
