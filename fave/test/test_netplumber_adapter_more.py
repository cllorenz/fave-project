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

""" More unit tests for netplumber.adapter.NetPlumberAdapter, complementing
test_adapter.py: declared-LPM ordering, rewrites, slices, links, the
incremental update API (INCREMENTAL_PLAN.md §6.2/§6.3), generator and probe
removal, probe test paths, and the pass-through calls.

As in test_adapter.py the module's ``jsonrpc`` is patched, so every RPC is
recorded rather than sent: what is pinned is what the adapter TELLS NetPlumber
and the bookkeeping it keeps. No backend, no socket.

Several defects are PINNED as measured (2026-10-14), each in a test whose name
ends in KNOWN_DEFECT, so a fix fails it visibly instead of passing unnoticed;
the docstring says what the correct behaviour would be.
"""

import io
import logging
import contextlib
import unittest
from unittest import mock

from aggregator.aggregator_abstract import TRACE
from aggregator.abstract_engine import UpdateRefused
from devices.abstract_device import AbstractDeviceModel, LPM
from devices.generator import GeneratorModel
from devices.packet_filter import PacketFilterModel
from devices.probe import ProbeModel
from devices.router import RouterModel
from devices.switch import SwitchModel
from netplumber.adapter import (
    NetPlumberAdapter, LpmOrderingError,
    _lpm_index, _calc_rule_index, _LPM_BAND, _LPM_IDX_MAX,
)
from netplumber.slice import Slice
from netplumber.vector import Vector, get_field_from_vector
from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite, Miss

_LOGGER = 'test_netplumber_adapter_more'
_DST = 'packet.ipv4.destination'


def _route(idx, prefix, out='sw.2', node='sw', negated=False):
    match = Match([RuleField(_DST, prefix, negated=negated)]) if prefix else Match()
    return Rule(node, node + '.1', idx, in_ports=[node + '.1'],
                match=match, actions=[Forward([out])])


def _gen(name='gen'):
    return GeneratorModel(name, {'ipv4_src': [RuleField('ipv4_src', '10.0.0.1')]})


class _Base(unittest.TestCase):
    """ An adapter whose jsonrpc is a recording mock. """

    def setUp(self):
        patcher = mock.patch('netplumber.adapter.jsonrpc')
        self.rpc = patcher.start()
        self.addCleanup(patcher.stop)
        # add_rules_batch answers one engine id per rule sent
        self.rpc.add_rules_batch.side_effect = \
            lambda _socks, batch: [1000 + i for i in range(len(batch))]
        self.log = logging.getLogger(_LOGGER)
        self.log.setLevel(logging.WARNING)
        self.adapter = NetPlumberAdapter(['SOCK'], self.log)

    def switch(self, name='sw', rules=None, lpm=False):
        """ A switch with its tables added (and optionally declared LPM). """
        model = SwitchModel(name, ports=['1', '2'])
        if lpm:
            model.set_table_semantics(name + '.1', LPM)
        self.adapter.add_tables(model)
        if rules is not None:
            model.tables[name + '.1'] = rules
        return model

    def sent_batch(self, call=-1):
        return self.rpc.add_rules_batch.call_args_list[call].args[1]


class TestLpmIndex(unittest.TestCase):
    """ `_lpm_index`: band by prefix length, longest first, then model index. """

    def test_longest_prefix_gets_the_lowest_band(self):
        self.assertEqual(_lpm_index(128, 0), 1)
        self.assertEqual(_lpm_index(32, 5), (128 - 32) * _LPM_BAND + 6)
        self.assertEqual(_lpm_index(-1, 0), 129 * _LPM_BAND + 1)
        self.assertLess(_lpm_index(24, 99), _lpm_index(8, 0))

    def test_invert_puts_the_default_route_first(self):
        self.assertEqual(_lpm_index(-1, 0, invert=True), 1)
        self.assertLess(_lpm_index(8, 0, invert=True), _lpm_index(24, 0, invert=True))

    def test_the_whole_range_fits_32_bits(self):
        self.assertLess(_lpm_index(-1, _LPM_IDX_MAX), 2**32)

    def test_an_index_outside_the_band_is_refused(self):
        for idx in (-1, _LPM_IDX_MAX + 1):
            with self.subTest(idx=idx), self.assertRaises(LpmOrderingError):
                _lpm_index(24, idx)


class TestPassThroughCalls(_Base):
    """ Calls that only forward to the RPC layer with the adapter's sockets. """

    def test_dumps_stop_anomalies_and_tracking(self):
        self.adapter.stop()
        self.adapter.dump_flows('/o')
        self.adapter.dump_plumbing_network('/o')
        self.adapter.dump_pipes('/o')
        self.adapter.dump_flow_trees('/o', keep_simple=True)
        self.adapter.check_anomalies(use_reach=True)
        self.adapter.track_affected(True)

        self.rpc.stop.assert_called_once_with(['SOCK'])
        self.rpc.dump_flows.assert_called_once_with(['SOCK'], '/o')
        self.rpc.dump_plumbing_network.assert_called_once_with(['SOCK'], '/o')
        self.rpc.dump_pipes.assert_called_once_with(['SOCK'], '/o')
        self.rpc.dump_flow_trees.assert_called_once_with(['SOCK'], '/o', True)
        self.rpc.check_anomalies.assert_called_once_with(
            ['SOCK'], use_shadow=False, use_reach=True, use_general=False)
        self.rpc.set_track_affected.assert_called_once_with(['SOCK'], True)

    def test_configuration_stamp_always_carries_the_lpm_inversion(self):
        stamp = self.adapter.configuration_stamp()
        self.assertEqual(stamp, {
            'impl': NetPlumberAdapter.IMPL,
            'upstream': NetPlumberAdapter.UPSTREAM,
            'np_invert_lpm': False,
        })
        inverted = NetPlumberAdapter(['SOCK'], self.log, invert_lpm=True)
        self.assertIs(inverted.configuration_stamp()['np_invert_lpm'], True)

    def test_a_mapping_given_as_json_is_adopted(self):
        adapter = NetPlumberAdapter(
            ['SOCK'], self.log, mapping={'length': 32, _DST: 0})
        self.assertEqual(adapter.mapping.length, 32)
        self.assertEqual(adapter.mapping_keys, {_DST})


class TestLinks(_Base):
    """ Link calls translate port names to global port numbers. """

    def setUp(self):
        super().setUp()
        self.sw = self.switch()
        self.rpc.add_source.return_value = 501
        self.adapter.add_generator(_gen())
        self.g = self.adapter.global_port

    def test_add_link_uses_global_ports(self):
        self.adapter.add_link('sw.1', 'sw.2')
        self.rpc.add_link.assert_called_once_with(
            ['SOCK'], self.g('sw.1'), self.g('sw.2'))

    def test_add_links_bulk_attaches_the_source_index(self):
        """ A link from a generator carries that generator's table index (its
        shard); any other link the broadcast sentinel -1. """
        self.adapter.add_links_bulk([('gen.1', 'sw.1'), ('sw.2', 'sw.1')])
        self.rpc.add_links_bulk.assert_called_once_with(
            ['SOCK'],
            [(self.adapter.generators['gen'][0], self.g('gen.1'), self.g('sw.1')),
             (-1, self.g('sw.2'), self.g('sw.1'))],
            use_dynamic=False)

    def test_remove_link_drops_the_bookkeeping_entry(self):
        """ remove_link takes GLOBAL ports (the aggregator converts them) and
        drops a source's entry once its last link is gone. """
        self.adapter.links = {7: [8, 9]}
        self.adapter.remove_link(7, 8)
        self.assertEqual(self.adapter.links, {7: [9]})
        self.adapter.remove_link(7, 9)
        self.assertEqual(self.adapter.links, {})
        self.assertEqual(self.rpc.remove_link.call_args_list,
                         [mock.call(['SOCK'], 7, 8), mock.call(['SOCK'], 7, 9)])

    def test_set_link_up_and_down(self):
        self.adapter.set_link('sw.1', 'sw.2', True)
        self.assertEqual(self.adapter.links, {self.g('sw.1'): [self.g('sw.2')]})
        self.adapter.set_link('sw.1', 'sw.2', False)
        self.assertEqual(self.adapter.links, {})
        self.rpc.add_link.assert_called_once_with(
            ['SOCK'], self.g('sw.1'), self.g('sw.2'))
        self.rpc.remove_link.assert_called_once_with(
            ['SOCK'], self.g('sw.1'), self.g('sw.2'))

    def test_set_link_down_on_an_unknown_link_only_sends_the_rpc(self):
        self.adapter.set_link('sw.2', 'sw.1', False)
        self.rpc.remove_link.assert_called_once()
        self.assertEqual(self.adapter.links, {})


class TestSlices(_Base):
    """ Network slices become header vectors over the adapter's mapping. """

    def test_add_slice_builds_vectors_and_expands_the_mapping(self):
        slicem = Slice(3, ns_list=[[RuleField(_DST, '10.0.0.0/8')]])
        self.adapter.add_slice(slicem)

        self.rpc.expand.assert_called_once_with(['SOCK'], 32)
        socks, sid, ns_list, ns_diff = self.rpc.add_slice.call_args.args
        self.assertEqual((socks, sid, ns_diff), (['SOCK'], 3, None))
        self.assertEqual([v.vector for v in ns_list], ['00001010' + 'x' * 24])

    def test_a_slice_diff_is_passed_through(self):
        slicem = Slice(4, ns_list=[[RuleField(_DST, '10.0.0.0/8')]],
                       ns_diff=[[RuleField(_DST, '10.1.0.0/16')]])
        self.adapter.add_slice(slicem)
        ns_diff = self.rpc.add_slice.call_args.args[3]
        self.assertEqual([v.vector for v in ns_diff],
                         ['0000101000000001' + 'x' * 16])

    def test_del_slice(self):
        self.adapter.del_slice(4)
        self.rpc.remove_slice.assert_called_once_with(['SOCK'], 4)


class TestCheckCompliance(_Base):
    """ check_compliance sends {probe node id: [(source node id, must reach,
    condition vector)]}. """

    def test_rules_are_sent_with_engine_node_ids(self):
        self.rpc.add_source.return_value = 501
        self.rpc.add_source_probe.return_value = 601
        self.adapter.add_generator(_gen())
        self.adapter.add_probe(ProbeModel(
            'pr', 'universal',
            test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]}))

        self.adapter.check_compliance({'pr': [('gen', False, None)]})
        self.rpc.check_compliance.assert_called_once_with(
            ['SOCK'], {601: [(501, True, None)]})


class TestDeclaredLpmTables(_Base):
    """ A table declared longest-prefix-match is sent longest prefix first,
    with `_lpm_index` as the NetPlumber index; local rule identity keeps the
    model index (TABLE_SEMANTICS_PLAN.md S3, INCREMENTAL_PLAN.md O1). """

    def setUp(self):
        super().setUp()
        self.rules = [_route(0, None), _route(1, '10.0.0.0/8'),
                      _route(2, '10.1.2.0/24')]

    def test_longest_prefix_first(self):
        sw = self.switch(rules=self.rules, lpm=True)
        with self.assertLogs(_LOGGER, level='INFO') as logs:
            self.adapter.add_rules(sw)
        self.assertIn("longest-first", logs.output[-1])

        batch = self.sent_batch()
        self.assertEqual([r[2] for r in batch],
                         [_lpm_index(24, 2), _lpm_index(8, 1), _lpm_index(-1, 0)])
        tid = self.adapter.tables['sw.1']
        self.assertEqual([r[0] for r in batch],
                         [_calc_rule_index(i, t_idx=tid) for i in (2, 1, 0)])
        self.assertEqual(self.adapter.rule_ids[_calc_rule_index(2, t_idx=tid)], [1000])

    def test_the_guardrail_inverts_the_order(self):
        adapter = NetPlumberAdapter(['SOCK'], self.log, invert_lpm=True)
        self.adapter = adapter
        sw = self.switch(rules=self.rules, lpm=True)
        with self.assertLogs(_LOGGER, level='INFO') as logs:
            adapter.add_rules(sw)
        self.assertIn("SHORTEST-first", logs.output[-1])
        self.assertEqual([r[2] for r in self.sent_batch()],
                         [_lpm_index(-1, 0, True), _lpm_index(8, 1, True),
                          _lpm_index(24, 2, True)])

    def test_an_undeclared_table_keeps_the_model_index(self):
        sw = self.switch(rules=self.rules)
        self.adapter.add_rules(sw)
        self.assertEqual([r[2] for r in self.sent_batch()],
                         [_calc_rule_index(i) for i in (0, 1, 2)])

    def test_a_negated_route_is_refused(self):
        sw = self.switch(rules=[_route(0, '10.0.0.0/8', negated=True)], lpm=True)
        with self.assertRaises(LpmOrderingError):
            self.adapter.add_rules(sw)
        self.rpc.add_rules_batch.assert_not_called()

    def test_an_inserted_route_takes_its_build_slot(self):
        """ O1: an insert gets exactly the index a build would have given. """
        sw = self.switch(rules=self.rules[:2], lpm=True)
        self.adapter.add_rules(sw)
        self.adapter.insert_rule(self.rules[2])
        self.assertEqual(self.sent_batch()[0][2], _lpm_index(24, 2))


class TestRewritesAndActions(_Base):
    """ `_prepare_generic_rule`: rewrite/mask vectors, port values, unknown
    actions. """

    def test_rewrite_of_a_port_field_writes_its_global_number(self):
        rule = Rule('sw', 'sw.1', 0, in_ports=['sw.1'],
                    match=Match([RuleField(_DST, '10.0.0.0/8')]),
                    actions=[Rewrite([RuleField('in_port', 'sw.2')]),
                             Forward(['sw.2'])])
        sw = self.switch(rules=[rule])
        self.adapter.add_rules(sw)

        mapping = self.adapter.mapping
        _np, _tid, _idx, _in, out, match, mask, rewrite = self.sent_batch()[0]
        self.assertEqual(out, [self.adapter.global_port('sw.2')])
        self.assertEqual(
            get_field_from_vector(mapping, Vector.from_vector_str(rewrite), 'in_port'),
            '{:032b}'.format(self.adapter.global_port('sw.2')))
        self.assertEqual(
            get_field_from_vector(mapping, Vector.from_vector_str(mask), 'in_port'),
            '1' * 32)
        self.assertEqual(
            get_field_from_vector(mapping, Vector.from_vector_str(mask), _DST),
            '0' * 32)
        self.assertEqual(
            get_field_from_vector(mapping, Vector.from_vector_str(match), _DST),
            '00001010' + 'x' * 24)

    def test_an_unknown_action_is_ignored_with_a_warning(self):
        rule = Rule('sw', 'sw.1', 0, in_ports=['sw.1'], match=Match(),
                    actions=[Miss(), Forward(['sw.2'])])
        sw = self.switch(rules=[rule])
        with self.assertLogs(_LOGGER, level='WARNING') as logs:
            self.adapter.add_rules(sw)
        self.assertIn("ignore unknown action", logs.output[0])
        _np, _t, _i, _in, out, _m, mask, rewrite = self.sent_batch()[0]
        self.assertEqual((out, mask, rewrite),
                         ([self.adapter.global_port('sw.2')], None, None))

    def test_add_generic_table_sends_one_rule_per_negation(self):
        """ The per-rule path: a negated /8 expands into 8 engine rules, each
        recorded under its own negation slot. """
        self.rpc.add_rule.side_effect = range(10, 100)
        sw = self.switch(rules=[_route(3, '10.0.0.0/8', negated=True)])
        self.adapter._add_generic_table(sw, 'sw.1')

        self.assertEqual(self.rpc.add_rule.call_count, 8)
        indices = [c.args[2] for c in self.rpc.add_rule.call_args_list]
        self.assertEqual(indices, [_calc_rule_index(3, n_idx=n) for n in range(8)])
        tid = self.adapter.tables['sw.1']
        self.assertEqual(self.adapter.rule_ids[_calc_rule_index(3, t_idx=tid, n_idx=7)],
                         [17])


class TestRoutingTables(_Base):
    """ pre_routing / post_routing translation of a RouterModel. """

    def test_router_post_routing_pins_the_out_port(self):
        """ The router workaround writes the forwarding port into the match's
        out_port field, so a post_routing rule only matches its own port. """
        self.rpc.add_rule.side_effect = range(1, 100)
        router = RouterModel('r', ports=['1', '2'])
        self.adapter.add_tables(router)
        self.adapter.add_rules(router)

        tid = self.adapter.tables['r.post_routing']
        post = [c.args for c in self.rpc.add_rule.call_args_list if c.args[1] == tid]
        self.assertEqual(len(post), 4)
        mapping = self.adapter.mapping
        for _socks, _tid, _idx, _in, out_ports, match, _mask, _rw in post:
            if out_ports:   # the forwarding rules (filtering ones forward nowhere)
                self.assertEqual(
                    get_field_from_vector(mapping, Vector.from_vector_str(match),
                                          'out_port'),
                    '{:032b}'.format(out_ports[0]))

    def test_serialised_routing_rules_translate_like_rule_objects(self):
        """ pre/post_routing tables may hold rules still in their JSON form;
        they are parsed and sent exactly as the Rule objects would be. """
        sent = []
        for serialise in (False, True):
            self.rpc.reset_mock()
            self.rpc.add_rule.side_effect = range(1, 100)
            self.adapter = NetPlumberAdapter(['SOCK'], self.log)
            router = RouterModel('r', ports=['1', '2'])
            if serialise:
                for table in ('r.pre_routing', 'r.post_routing'):
                    router.tables[table] = [r.to_json() for r in router.tables[table]]
            self.adapter.add_tables(router)
            self.adapter.add_rules(router)
            sent.append([c.args for c in self.rpc.add_rule.call_args_list])
        self.assertEqual(len(sent[0]), 6)
        self.assertEqual(sent[0], sent[1])

    def test_pre_routing_extends_the_mapping_with_an_expand(self):
        """ When `in_port` is not yet mapped, `_add_pre_routing_rules` extends
        the mapping through `_update_mapping`, so `expand(64)` reaches
        NetPlumber before the 64-bit rule. It once extended the mapping alone:
        NetPlumber was told 32 bits and sent a 64-bit rule (TODO item 53). """
        model = AbstractDeviceModel(
            'd', tables={'d.pre_routing': [Rule(
                'd', 'd.pre_routing', 0, in_ports=['d.in'],
                match=Match([RuleField(_DST, '10.0.0.0/8')]),
                actions=[Forward(['d.out'])])]},
            ports={'d.in': 'd.pre_routing', 'd.out': 'd.pre_routing'})
        self.rpc.add_rule.return_value = 5
        self.adapter.add_tables(model)
        self.adapter.add_rules(model)

        self.assertEqual([c.args[1] for c in self.rpc.expand.call_args_list], [32, 64])
        self.assertEqual(len(self.rpc.add_rule.call_args.args[5]), 64)
        self.assertIn('in_port', self.adapter.mapping_keys)

class TestIncrementalUpdates(_Base):
    """ insert_rule / delete_rule on a built model, and what they refuse. """

    def setUp(self):
        super().setUp()
        self.sw = self.switch(rules=[_route(0, '10.0.0.0/8')])
        self.adapter.add_rules(self.sw)
        self.tid = self.adapter.tables['sw.1']

    def test_insert_then_delete_a_negated_rule(self):
        """ Insert sends every negation expansion; delete removes every engine
        rule of every slot and forgets them. """
        self.adapter.insert_rule(_route(5, '10.0.0.0/8', negated=True))
        self.assertEqual(len(self.sent_batch()), 8)
        engine_ids = [self.adapter.rule_ids[_calc_rule_index(5, t_idx=self.tid, n_idx=n)][0]
                      for n in range(8)]

        self.adapter.delete_rule('sw', 'sw.1', 5)
        self.assertEqual([c.args[1] for c in self.rpc.remove_rule.call_args_list],
                         engine_ids)
        self.assertFalse(any(
            _calc_rule_index(5, t_idx=self.tid, n_idx=n) in self.adapter.rule_ids
            for n in range(8)))
        # the other rule is untouched
        self.assertIn(_calc_rule_index(0, t_idx=self.tid), self.adapter.rule_ids)

    def test_inserting_a_present_rule_is_refused(self):
        with self.assertRaises(UpdateRefused):
            self.adapter.insert_rule(_route(0, '10.2.0.0/16'))

    def test_deleting_an_absent_rule_is_refused(self):
        with self.assertRaises(UpdateRefused):
            self.adapter.delete_rule('sw', 'sw.1', 9)
        self.rpc.remove_rule.assert_not_called()

    def test_routing_tables_and_unknown_tables_are_refused(self):
        for tid in ('fw.pre_routing', 'fw.post_routing', 'nope.1'):
            with self.subTest(tid=tid):
                with self.assertRaises(UpdateRefused):
                    self.adapter.delete_rule('fw', tid, 0)
                rule = Rule('x', tid, 1, match=Match(), actions=[])
                with self.assertRaises(UpdateRefused):
                    self.adapter.insert_rule(rule)


class TestTakeAffected(_Base):
    """ Engine node-id pairs are translated back to FaVe names. """

    def setUp(self):
        super().setUp()
        self.rpc.add_source.return_value = 501
        self.rpc.add_source_probe.return_value = 601
        self.adapter.add_generator(_gen())
        self.adapter.add_probe(ProbeModel(
            'pr', 'universal',
            test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]}))

    def test_known_pairs_are_named_and_unknown_dropped(self):
        self.rpc.take_affected.return_value = {(501, 601), (501, 999), (998, 601)}
        self.assertEqual(self.adapter.take_affected(), {('gen', 'pr')})
        self.rpc.take_affected.assert_called_once_with(['SOCK'])

    def test_a_deleted_source_and_probe_are_no_longer_reported(self):
        """ delete_generator and delete_probe drop the node from
        `generators`/`probes`, so take_affected drops pairs naming it, as its
        docstring promises. They once kept it (TODO item 53). """
        self.adapter.links[self.adapter.global_port('gen.1')] = [
            self.adapter.global_port('pr.1')]
        self.adapter.delete_generator('gen')
        self.adapter.delete_probe('pr')
        self.assertNotIn('gen', self.adapter.generators)
        self.assertNotIn('pr', self.adapter.probes)
        self.rpc.take_affected.return_value = {(501, 601)}
        self.assertEqual(self.adapter.take_affected(), set())


class TestGeneratorRemoval(_Base):
    """ delete_generator removes its links and its source; re-adding a
    generator replaces the old one. """

    def setUp(self):
        super().setUp()
        self.sw = self.switch()
        self.rpc.add_source.side_effect = [501, 502]
        self.adapter.add_generator(_gen())
        self.gport = self.adapter.global_port('gen.1')
        targets = [self.adapter.global_port(p) for p in ('sw.1', 'sw.2')]
        self.adapter.links[self.gport] = list(targets)
        self.targets = targets

    def test_delete_removes_its_link_and_source(self):
        self.adapter.links[self.gport] = [self.targets[0]]
        self.adapter.delete_generator('gen')
        self.rpc.remove_link.assert_called_once_with(
            ['SOCK'], self.gport, self.targets[0])
        self.rpc.remove_source.assert_called_once_with(['SOCK'], 501)
        self.assertNotIn(self.gport, self.adapter.links)
        self.assertNotIn('gen', self.adapter.tables)

    def test_delete_with_several_links_removes_them_all(self):
        """ The loop once removed links from the very list it walked, so with
        two links only the first went (TODO item 53). """
        self.adapter.delete_generator('gen')
        self.assertEqual(
            [c.args for c in self.rpc.remove_link.call_args_list],
            [(['SOCK'], self.gport, t) for t in self.targets])
        self.assertNotIn(self.gport, self.adapter.links)
        self.rpc.remove_source.assert_called_once_with(['SOCK'], 501)

    def test_re_adding_replaces_the_source(self):
        self.adapter.add_generator(_gen())
        self.rpc.remove_source.assert_called_once_with(['SOCK'], 501)
        idx, sid, _model = self.adapter.generators['gen']
        self.assertEqual(sid, 502)
        self.assertEqual(self.adapter.tables['gen'], idx)

    def test_re_adding_an_unlinked_generator_replaces_it(self):
        """ A generator with no link yet once made delete_generator raise
        KeyError, so it could not be re-added (TODO item 53). """
        self.rpc.add_source.side_effect = [601, 602]
        self.adapter.add_generator(_gen('lonely'))
        self.adapter.add_generator(_gen('lonely'))
        self.rpc.remove_source.assert_called_once_with(['SOCK'], 601)
        self.assertEqual(self.adapter.generators['lonely'][1], 602)


class TestProbes(_Base):
    """ Probe test expressions, test paths and removal. """

    def setUp(self):
        super().setUp()
        self.rpc.add_source_probe.side_effect = range(601, 700)

    def _test_expr(self):
        return self.rpc.add_source_probe.call_args.args[5]

    def test_fields_only_give_a_true_test(self):
        self.adapter.add_probe(ProbeModel(
            'pr', 'existential',
            match=Match([RuleField(_DST, '10.0.0.0/8')]),
            test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]}))
        socks, ports, quantor, match, filt, test, idx = \
            self.rpc.add_source_probe.call_args.args
        self.assertEqual((socks, quantor, filt, test), (['SOCK'], 'existential',
                                                         None, {"type": "true"}))
        self.assertEqual(ports, [self.adapter.global_port('pr.1')])
        self.assertEqual(idx, self.adapter.tables['pr'])
        self.assertEqual(match, '00001010' + 'x' * 24)

    def test_every_pathlet_kind_is_translated(self):
        """ Ports become global port numbers, tables become table indices --
        the post_routing table for a packet filter, `<node>.1` otherwise. """
        sw = self.switch()
        fw = PacketFilterModel('fw', ports=['1', '2'])
        self.adapter.add_tables(fw)
        path = ['start', '.*(port=sw.1)', '(port in (sw.1,sw.2))',
                '.*(port in (sw.2))$', '.*(table=sw)', '(table in (sw,fw))',
                '.*(table in (fw))$', 'skip', 'skip_next', 'end']
        self.adapter.add_probe(ProbeModel(
            'pr', 'universal',
            test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]},
            test_path=path))
        del sw

        g = self.adapter.global_port
        sw_t, fw_t = self.adapter.tables['sw.1'], self.adapter.tables['fw.post_routing']
        self.assertEqual(self._test_expr(), {"type": "path", "pathlets": [
            {"type": "start"},
            {"type": "port", "port": g('sw.1')},
            {"type": "next_ports", "ports": [g('sw.1'), g('sw.2')]},
            {"type": "last_ports", "ports": [g('sw.2')]},
            {"type": "table", "table": sw_t},
            {"type": "next_tables", "tables": [sw_t, fw_t]},
            {"type": "last_tables", "tables": [fw_t]},
            {"type": "skip"}, {"type": "skip_next"}, {"type": "end"},
        ]})

    def test_a_path_without_fields_is_a_path_test(self):
        """ With an empty mapping the empty test header space is falsy, so the
        path alone decides. """
        self.switch()
        self.adapter.add_probe(ProbeModel('pr', 'universal', test_path=['.*(port=sw.2)']))
        self.assertEqual(self._test_expr(), {"type": "path", "pathlets": [
            {"type": "port", "port": self.adapter.global_port('sw.2')}]})

    def test_neither_fields_nor_path_is_reported_and_not_sent(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.adapter.add_probe(ProbeModel('pr', 'universal'))
        self.assertIn("no test fields or path", err.getvalue())
        self.rpc.add_source_probe.assert_not_called()
        self.assertNotIn('pr', self.adapter.probes)

    def test_delete_probe_removes_inbound_links_and_the_probe(self):
        self.adapter.add_probe(ProbeModel(
            'pr', 'universal',
            test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]}))
        pport = self.adapter.global_port('pr.1')
        self.adapter.links = {1: [pport], 2: [pport, 3], 4: [5]}

        self.adapter.delete_probe('pr')
        self.assertEqual(self.adapter.links, {2: [3], 4: [5]})
        self.assertEqual(sorted(c.args[1:] for c in self.rpc.remove_link.call_args_list),
                         [(1, pport), (2, pport)])
        self.rpc.remove_source_probe.assert_called_once_with(['SOCK'], 601)
        self.assertNotIn('pr', self.adapter.tables)

    def test_re_adding_a_probe_replaces_it(self):
        probe = ProbeModel('pr', 'universal',
                           test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]})
        self.adapter.add_probe(probe)
        self.adapter.add_probe(probe)
        self.rpc.remove_source_probe.assert_called_once_with(['SOCK'], 601)
        self.assertEqual(self.adapter.probes['pr'][1], 602)


class TestModelRemovalDeadCode(_Base):
    """ delete_rules / delete_wiring / delete_tables, reached only from
    AggregatorService._delete_model, which nothing calls (its call site is
    commented out: "TODO: fix deletion"). All three are broken; the defects
    are pinned so reviving the path meets them here first. """

    def test_delete_rules_KNOWN_DEFECT(self):
        """ adapter.py:1069-1071: indexes a Rule as a tuple (`x[0]`) and would
        then pass the table NAME as `t_idx` to `_calc_rule_index`. Correct:
        remove every engine rule of the model and forget it. """
        sw = self.switch(rules=[_route(0, '10.0.0.0/8')])
        self.adapter.add_rules(sw)
        with self.assertRaises(TypeError):
            self.adapter.delete_rules(sw)
        self.rpc.remove_rule.assert_not_called()

    def test_delete_tables_KNOWN_DEFECT(self):
        """ adapter.py:1118: `if not self.tables[table]` removes only a table
        whose index is 0 -- and indices start at 1. Correct: remove_table for
        every table of the model. """
        sw = self.switch()
        self.adapter.delete_tables(sw)
        self.rpc.remove_table.assert_not_called()
        self.assertIn('sw.1', self.adapter.tables)

        self.adapter.tables['sw.1'] = 0          # the only index it removes
        self.adapter.delete_tables(sw)
        self.rpc.remove_table.assert_called_once_with(['SOCK'], 0)
        self.assertNotIn('sw.1', self.adapter.tables)

    def test_delete_wiring_KNOWN_DEFECT(self):
        """ adapter.py:1087-1093: a port's table is guessed by stripping its
        last dotted component, so `fw.pre_routing_input` resolves to `fw`, not
        a table. Correct: remove_link for each internal wire. """
        fw = PacketFilterModel('fw', ports=['1', '2'])
        self.adapter.add_tables(fw)
        with self.assertRaises(KeyError):
            self.adapter.delete_wiring(fw)

    def test_delete_wiring_where_the_guess_happens_to_hold(self):
        """ When a port IS `<table>.<n>` the wire is removed by packed port. """
        model = AbstractDeviceModel(
            'm', tables={'m.a': [], 'm.b': []},
            ports={'m.a.1': 'm.a', 'm.b.1': 'm.b'},
            wiring=[('m.a.1', 'm.b.1')])
        self.adapter.add_tables(model)
        self.adapter.delete_wiring(model)
        self.rpc.remove_link.assert_called_once_with(
            ['SOCK'], self.adapter.global_port('m.a.1'),
            self.adapter.global_port('m.b.1'))


class TestDiagnosticLogging(_Base):
    """ The DEBUG and TRACE narration of a whole build names what it sends. """

    def test_a_full_build_narrates_each_step(self):
        self.rpc.add_rule.side_effect = range(1, 1000)
        self.rpc.add_source.return_value = 501
        self.rpc.add_sources_bulk.side_effect = \
            lambda _s, srcs, use_dynamic: {s[0]: 700 + s[0] for s in srcs}
        self.rpc.add_source_probe.return_value = 601
        fw = PacketFilterModel('fw', ports=['1', '2'])
        fw.set_address('10.0.0.1')
        router = RouterModel('r', ports=['1', '2'])
        sw = SwitchModel('sw', ports=['1', '2'])
        sw.tables['sw.1'] = [_route(0, '10.0.0.0/8')]

        with self.assertLogs(_LOGGER, level=TRACE) as logs:
            for model in (fw, router, sw):
                self.adapter.add_tables(model)
                self.adapter.add_wiring(model)
                self.adapter.add_wiring(model)       # every wire now exists
                self.adapter.add_rules(model)
            self.adapter.add_generators_bulk([_gen('g1'), _gen('g2')])
            self.adapter.add_generator(_gen('g3'))
            self.adapter.add_probe(ProbeModel(
                'pr', 'universal',
                test_fields={'ipv4_dst': [RuleField('ipv4_dst', '10.0.0.2')]}))
            self.adapter._add_generic_table(sw, 'sw.1')
            self.adapter.add_slice(Slice(1, ns_list=[[RuleField(_DST, '10.0.0.0/8')]]))
            self.adapter.del_slice(1)
            self.adapter.links[self.adapter.global_port('g3.1')] = [
                self.adapter.global_port('pr.1')]
            self.adapter.delete_probe('pr')
            self.adapter.links[self.adapter.global_port('g3.1')] = [1]
            self.adapter.delete_generator('g3')
            model = AbstractDeviceModel(
                'm', tables={'m.a': []}, ports={'m.a.1': 'm.a'},
                wiring=[('m.a.1', 'm.a.1')])
            self.adapter.add_tables(model)
            self.adapter.delete_wiring(model)
            self.adapter.add_wiring(AbstractDeviceModel(
                'f', wiring=[('f.internals_in', 'm.a.1')]))
            self.adapter.tables['m.a'] = 0
            self.adapter.delete_tables(model)

        text = "\n".join(logs.output)
        for expected in (
                "update rules for model fw",         # TRACE
                "add table to netplumber: fw.pre_routing",
                "skip forbidden wire", "skip existing wire",
                "add link to netplumber", "add a batch of",
                "add rule", "add source g1", "add source g3",
                "add probe pr", "add slice 1", "remove slice 1",
                "remove probe 601", "remove source g3", "remove link",
                "remove table m.a"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertEqual(self.adapter.generators['g2'][1], 700 + self.adapter.generators['g2'][0])


if __name__ == '__main__':
    unittest.main()
