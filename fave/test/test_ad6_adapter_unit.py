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

""" `Ad6Adapter` with the bridge subprocess MOCKED: the fast-tier unit tests.

The adapter does three things on FaVe's side of the subprocess boundary --
validate and stamp its configuration, buffer the model the aggregator hands it,
and build the payload the bridge solves. All three are pure Python; only the
bridge needs a solver. Here `subprocess.run` is replaced by a fake that records
the payload and writes a canned answer, so these tests pin:

  * which configurations the constructor REFUSES (unknown grounding/solver,
    an assumption-ignoring solver under rank grounding, the deleted
    translation) and what `configuration_stamp` reports;
  * what the buffering methods record, including declared table semantics and
    generator source prefixes;
  * the payload's shape (config XML WITHOUT the namespace that would empty the
    model on re-parse, query nodes, widths, recipes) and how bridge answers
    become compliance VIOLATIONS;
  * that a failing bridge raises with its stderr, and that the not-implemented
    surface refuses rather than pretending.
"""

import json
import logging
import unittest

from types import SimpleNamespace
from unittest import mock

import lxml.etree as et

from ad6 import adapter as ad6_adapter
from ad6.adapter import Ad6Adapter
from aggregator.abstract_engine import UpdateRefused
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField


def _log():
    log = logging.getLogger('test_ad6_adapter_unit')
    log.setLevel(logging.WARNING)
    return log


def _rules_model(node, tables, semantics=None):
    model = SimpleNamespace(node=node, tables=tables)
    if semantics is not None:
        model.semantics_of = lambda table: semantics.get(table, 'first_match')
    return model


def _network(adapter):
    """ g -> sw -> p, sw forwarding only 10.0.0.0/8. """
    rule = Rule('sw', 'sw.t', 0,
                match=Match([RuleField('packet.ipv4.destination', '10.0.0.0/8')]),
                actions=[Forward(['sw.2'])])
    adapter.add_tables(SimpleNamespace(node='sw'))
    adapter.add_rules(_rules_model('sw', {'sw.t': [rule]}))
    adapter.add_generators_bulk([SimpleNamespace(
        node='g', fields={'packet.ipv4.source': [RuleField('packet.ipv4.source',
                                                            '192.168.0.0/16')]})])
    adapter.add_probe(SimpleNamespace(node='p'))
    adapter.add_links_bulk([('g.1', 'sw.1'), ('sw.2', 'p.1')])


class _FakeBridge:
    """ Stands in for `subprocess.run`: captures the payload, writes `answer`
    to the --out path, returns `returncode`/`stderr`. """

    def __init__(self, answer=(), returncode=0, stderr=b''):
        self.answer = list(answer)
        self.returncode = returncode
        self.stderr = stderr
        self.argv = None
        self.kwargs = None
        self.payload = None

    def __call__(self, argv, **kwargs):
        self.argv, self.kwargs = argv, kwargs
        with open(argv[argv.index('--in') + 1], encoding='utf-8') as raw:
            self.payload = json.load(raw)
        if self.returncode == 0:
            with open(argv[argv.index('--out') + 1], 'w', encoding='utf-8') as raw:
                json.dump(self.answer, raw)
        return SimpleNamespace(returncode=self.returncode, stdout=b'',
                               stderr=self.stderr)


class TestConstruction(unittest.TestCase):

    def test_defaults_and_stamp(self):
        adapter = Ad6Adapter(_log())
        self.assertEqual(adapter.configuration_stamp(), {
            'impl': 'first-party', 'translation': 'literal',
            'grounding': 'rank', 'solver': 'minisat22', 'lite_acyclic': False})

    def test_lite_acyclic_is_reported_only_where_it_applies(self):
        self.assertTrue(Ad6Adapter(_log(), lite_acyclic=True).lite_acyclic_applies)
        flow = Ad6Adapter(_log(), grounding='flow', lite_acyclic=True)
        self.assertFalse(flow.lite_acyclic_applies)
        self.assertFalse(flow.configuration_stamp()['lite_acyclic'])

    def test_unknown_grounding_and_solver_are_refused(self):
        with self.assertRaises(ValueError):
            Ad6Adapter(_log(), grounding='bfs')
        with self.assertRaises(ValueError):
            Ad6Adapter(_log(), solver='z3')

    def test_an_assumption_ignoring_solver_is_refused_under_rank_only(self):
        with self.assertRaises(ValueError) as ctx:
            Ad6Adapter(_log(), solver='kissat404')
        self.assertIn("grounding='flow'", str(ctx.exception))
        self.assertEqual(Ad6Adapter(_log(), grounding='flow',
                                    solver='kissat404').solver, 'kissat404')

    def test_the_deleted_translation_is_refused_naming_the_commit(self):
        for name in ('semantic', 'interpreted'):
            with self.subTest(translation=name):
                with self.assertRaises(ValueError) as ctx:
                    Ad6Adapter(_log(), translation=name)
                self.assertIn('86114970', str(ctx.exception))

    def test_the_pre_rename_alias_is_normalised(self):
        self.assertEqual(Ad6Adapter(_log(), translation='structural').translation,
                         'literal')

    def test_an_unknown_translation_is_refused(self):
        with self.assertRaises(ValueError):
            Ad6Adapter(_log(), translation='magic')

    def test_available_reflects_the_bridge_script(self):
        with mock.patch.object(ad6_adapter.os.path, 'isfile', return_value=False):
            self.assertFalse(ad6_adapter.available())


class TestBuffering(unittest.TestCase):

    def setUp(self):
        self.adapter = Ad6Adapter(_log())

    def test_only_non_default_table_semantics_are_recorded(self):
        self.adapter.add_rules(_rules_model(
            'r', {'r.fib': ['f'], 'r.acl': ['a']}, semantics={'r.fib': 'lpm'}))
        self.assertEqual(self.adapter._table_semantics, {'r': {'r.fib': 'lpm'}})
        self.assertEqual(self.adapter._tables['r'], {'r.fib': ['f'], 'r.acl': ['a']})

    def test_wiring_accumulates_and_empty_wiring_records_nothing(self):
        self.adapter.add_wiring(SimpleNamespace(node='r', wiring=[('r.1', 'r.2')]))
        self.adapter.add_wiring(SimpleNamespace(node='r', wiring=[('r.2', 'r.3')]))
        self.adapter.add_wiring(SimpleNamespace(node='s', wiring=[]))
        self.assertEqual(self.adapter._wiring, {'r': [['r.1', 'r.2'], ['r.2', 'r.3']]})

    def test_generators_record_port_fields_and_source_prefix(self):
        self.adapter.add_generator(SimpleNamespace(node='g4', fields={
            'packet.ipv4.source': [RuleField('packet.ipv4.source', '10.0.0.0/8')],
            'packet.upper.dport': []}))
        self.adapter.add_generator(SimpleNamespace(node='g6', fields={
            'packet.ipv6.source': [RuleField('packet.ipv6.source', '2001:db8::/32')]}))
        self.adapter.add_generator(SimpleNamespace(node='g0'))
        self.assertEqual(self.adapter._generators,
                         {'g4': 'g4.1', 'g6': 'g6.1', 'g0': 'g0.1'})
        self.assertEqual(self.adapter._gen_src,
                         {'g4': '10.0.0.0/8', 'g6': '2001:db8::/32'})
        self.assertEqual(self.adapter._gen_fields['g0'], {})

    def test_probes_and_deletions(self):
        self.adapter.add_probe(SimpleNamespace(node='p'))
        self.adapter.add_generator(SimpleNamespace(node='g'))
        self.assertEqual(self.adapter._probes, {'p': 'p.1'})
        self.adapter.delete_probe('p')
        self.adapter.delete_generator('g')
        self.adapter.delete_generator('never-added')
        self.assertEqual((self.adapter._probes, self.adapter._generators), ({}, {}))

    def test_links_are_recorded_verbatim_in_order(self):
        self.adapter.add_link('a.1_egress', 'b.1_ingress')
        self.adapter.add_links_bulk([('b.2', 'c.1')], use_dynamic=True)
        self.assertEqual(self.adapter._raw_edges,
                         [['a.1_egress', 'b.1_ingress'], ['b.2', 'c.1']])

    def _two_devices(self):
        for node in ('r', 's'):
            self.adapter.add_rules(_rules_model(
                node, {node + '.fib': ['f']}, semantics={node + '.fib': 'lpm'}))
            self.adapter.add_wiring(SimpleNamespace(
                node=node, wiring=[(node + '.1', node + '.2')]))
        self.adapter.add_links_bulk([('g.1', 'r.1'), ('r.2', 's.1'), ('s.2', 'p.1')])
        return SimpleNamespace(node='r')

    def test_remove_device_drops_it_from_every_buffer(self):
        """ INCREMENTAL_PLAN.md §8.2 Q-R3: every check rebuilds from the
        buffers, so dropping the device there removes it. """
        model = self._two_devices()
        self.adapter.remove_device(model, [('g.1', 'r.1'), ('r.2', 's.1')])
        self.assertEqual(list(self.adapter._tables), ['s'])
        self.assertEqual(list(self.adapter._table_semantics), ['s'])
        self.assertEqual(list(self.adapter._wiring), ['s'])
        self.assertEqual(self.adapter._raw_edges, [['s.2', 'p.1']])
        # and the name can come back, under a fresh first batch
        self.adapter.add_rules(_rules_model('r', {'r.fib': ['f2']}))
        self.assertEqual(self.adapter._tables['r'], {'r.fib': ['f2']})

    def test_remove_device_refuses_an_unknown_link_and_drops_nothing(self):
        model = self._two_devices()
        before = (dict(self.adapter._tables), list(self.adapter._raw_edges))
        with self.assertRaises(UpdateRefused):
            self.adapter.remove_device(model, [('g.1', 'r.1'), ('x.1', 'r.3')])
        self.assertEqual((self.adapter._tables, self.adapter._raw_edges), before)

    def test_cond_to_json_normalises_rulefields_and_passes_dicts(self):
        plain = {'name': 'related', 'value': '0', 'negated': False}
        self.assertEqual(
            Ad6Adapter._cond_to_json([RuleField('related', '1', True), plain]),
            [{'name': 'related', 'value': '1', 'negated': True}, plain])
        self.assertEqual(Ad6Adapter._cond_to_json(None), [])


class TestPayload(unittest.TestCase):

    def setUp(self):
        self.adapter = Ad6Adapter(_log())
        _network(self.adapter)
        self.payload = self.adapter._build_literal()

    def test_the_config_reparses_without_a_namespace(self):
        root = et.fromstring(self.payload['config'])
        self.assertEqual(root.tag, 'config')
        self.assertIsNone(root.nsmap.get(None))
        # the unprefixed xpaths ad6 uses must still find the rules
        self.assertEqual(sorted(r.get('key') for r in root.xpath('//rule')),
                         ['fw_g_g_generator_r0', 'fw_p_p_probe__p_1_r0',
                          'fw_sw_sw_t__sw_1_r0'])

    def test_query_nodes_widths_and_recipes(self):
        self.assertEqual(self.payload['sources'], {'g': 'fw_g_g_generator_r0'})
        self.assertEqual(self.payload['probes'], {'p': 'fw_p_p_probe__p_1_r0'})
        self.assertEqual(self.payload['mutable_fields'], {})
        self.assertEqual(self.payload['query_fields'], {
            'packet.ipv4.destination': {'scope': 'global', 'kind': 'cidr',
                                        'direction': 'dst', 'version': '4'}})
        self.assertIn(['favenet_sw_2_out', 'favenet_p_1_in'], self.payload['edges'])

    def test_a_rewritten_vlan_declares_its_width(self):
        adapter = Ad6Adapter(_log())
        adapter.add_rules(_rules_model('s', {'s.t': [Rule(
            's', 's.t', 0, actions=[Forward(['s.2'])],
            match=Match([RuleField('related', '1')]))]}))
        adapter.add_rules(_rules_model('t', {'t.t': [Rule(
            't', 't.t', 0, actions=[
                Rewrite([RuleField('packet.ether.vlan', '5')]),
                Forward(['t.2'])])]}))
        self.assertEqual(adapter._build_literal()['mutable_fields'],
                         {'vlan': 12, 'related': 8})


class TestGeneratorMatches(unittest.TestCase):

    def test_a_generator_matched_field_no_device_rewrites_is_declared(self):
        """ wl_ifi with its router removed: nothing rewrites `vlan`, so a
        source's `vlan=48` stays a match on the generator's own rule -- and
        ad6 refuses a <fieldmatch> on a field `MutableFields` never declared.
        Found by the device-removal oracle (INCREMENTAL_PLAN.md §8.2). """
        adapter = Ad6Adapter(_log())
        _network(adapter)
        adapter.add_generator(SimpleNamespace(
            node='v', fields={'packet.ether.vlan': [
                RuleField('packet.ether.vlan', '48')]}))
        adapter.add_links_bulk([('v.1', 'sw.1')])
        self.assertIn('vlan', adapter._build_literal()['mutable_fields'])


class TestCheckCompliance(unittest.TestCase):

    def setUp(self):
        self.adapter = Ad6Adapter(_log(), grounding='flow', solver='cadical195')
        _network(self.adapter)

    def _check(self, bridge, rules):
        with mock.patch.object(ad6_adapter.subprocess, 'run', bridge):
            self.adapter.check_compliance(rules)

    def test_the_payload_carries_queries_and_configuration(self):
        bridge = _FakeBridge()
        cond = [RuleField('packet.upper.dport', '22')]
        self._check(bridge, {'p': [('g', False, cond)]})
        self.assertEqual(bridge.argv[1], ad6_adapter.BRIDGE)
        self.assertEqual(bridge.kwargs['cwd'], ad6_adapter.AD6_ROOT)
        payload = bridge.payload
        self.assertEqual(payload['queries'], [{
            'source': 'g', 'probe': 'p', 'src_port': 'g.1', 'dst_port': 'p.1',
            'src_cidr': '192.168.0.0/16', 'negated': False,
            'cond': [{'name': 'packet.upper.dport', 'value': '22',
                      'negated': False}]}])
        self.assertEqual((payload['grounding'], payload['solver'],
                          payload['lite_acyclic'], payload['translation']),
                         ('flow', 'cadical195', False, 'literal'))
        self.assertIn('config', payload['literal'])

    def test_only_answers_contradicting_the_expectation_are_violations(self):
        answer = [
            {'source': 'g', 'probe': 'p', 'negated': False, 'reachable': False, 'cond': None},
            {'source': 'g', 'probe': 'p', 'negated': True, 'reachable': True, 'cond': 'c'},
            {'source': 'g', 'probe': 'p', 'negated': False, 'reachable': True, 'cond': 'ok'},
            {'source': 'g', 'probe': 'p', 'negated': True, 'reachable': False, 'cond': 'ok'},
        ]
        self._check(_FakeBridge(answer), {'p': [('g', False, None)]})
        self.assertEqual(self.adapter.get_compliance_results(),
                         [('g', 'p', True, ''), ('g', 'p', False, 'c')])
        self.adapter.clear_results()
        self.assertEqual(self.adapter.get_compliance_results(), [])

    def test_a_failing_bridge_raises_with_its_stderr_tail(self):
        bridge = _FakeBridge(returncode=3, stderr=b'x' * 5000 + b'BOOM')
        with self.assertRaises(RuntimeError) as ctx:
            self._check(bridge, {'p': [('g', False, None)]})
        message = str(ctx.exception)
        self.assertIn('rc=3', message)
        self.assertTrue(message.endswith('BOOM'))
        self.assertLess(len(message), 4100)
        self.assertEqual(self.adapter.get_compliance_results(), [])

    def test_an_unknown_probe_or_source_is_a_key_error_before_any_bridge_call(self):
        bridge = _FakeBridge()
        with self.assertRaises(KeyError):
            self._check(bridge, {'nope': [('g', False, None)]})
        with self.assertRaises(KeyError):
            self._check(bridge, {'p': [('nope', False, None)]})
        self.assertIsNone(bridge.argv)


class TestUnsupportedSurface(unittest.TestCase):

    def setUp(self):
        self.adapter = Ad6Adapter(_log())

    def test_unsupported_operations_raise(self):
        for method in ('check_anomalies', 'add_slice', 'del_slice'):
            with self.subTest(method=method):
                with self.assertRaises(NotImplementedError):
                    getattr(self.adapter, method)('x')

    def test_remove_link_is_refused_and_leaves_the_link(self):
        self.adapter.add_link('a.1', 'b.1')
        with self.assertRaises(UpdateRefused):
            self.adapter.remove_link('a.1', 'b.1')
        self.assertEqual(self.adapter._raw_edges, [['a.1', 'b.1']])

    def test_no_op_surface(self):
        for method in ('dump_flows', 'dump_flow_trees', 'dump_pipes',
                       'dump_plumbing_network', 'stop'):
            with self.subTest(method=method):
                self.assertIsNone(getattr(self.adapter, method)())
        self.assertEqual(self.adapter.global_port('sw.1'), 'sw.1')


if __name__ == '__main__':
    unittest.main()
