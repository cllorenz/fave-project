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

""" Tests for the aggregator service.

The aggregator orchestrates the verification backend but does not need it:
``AggregatorService`` takes ``engine`` and ``reporter`` injection seams (default
``None`` -> the production ``NetPlumberAdapter`` / ``Reporter``).  These tests
pass a recording ``MagicMock`` engine and a stub reporter so the queue-dispatch
(``_handler``) and model-diff (``_sync_diff``) logic can be exercised without a
live NetPlumber process or the log-tailing reporter daemon.
"""

import json
import logging
import os
import tempfile
import unittest

from unittest import mock

from aggregator.aggregator_service import AggregatorService, _parse_servers, build_parser
from devices.packet_filter import PacketFilterModel
from devices.switch import SwitchCommand
from netplumber.slice import SlicingCommand
from netplumber.slice import Slice


class TestParseServers(unittest.TestCase):
    """ Tests the backend server-list parser (host:port vs unix socket). """

    def test_single_tcp_server(self):
        self.assertEqual(_parse_servers('127.0.0.1:44001'), [('127.0.0.1', 44001)])

    def test_multiple_tcp_servers(self):
        self.assertEqual(
            _parse_servers('127.0.0.1:44001,10.0.0.1:44002'),
            [('127.0.0.1', 44001), ('10.0.0.1', 44002)]
        )

    def test_unix_socket_has_zero_port(self):
        """ A path without host:port is treated as a unix socket (port 0). """
        self.assertEqual(
            _parse_servers('/dev/shm/np.socket'), [('/dev/shm/np.socket', 0)]
        )


class _AggregatorTestBase(unittest.TestCase):
    """ Builds an AggregatorService with a recording engine + stub reporter.

    No sockets, no backend, no reporter daemon: both production dependencies
    are replaced via the constructor's injection seams.
    """

    def setUp(self):
        # Keep the worker's INFO/DEBUG/TRACE branches quiet (and TRACE off, so
        # the plain stdlib logger -- which lacks .trace() -- is never called).
        logging.getLogger('Aggregator').setLevel(logging.WARNING)
        self.engine = mock.MagicMock(name='engine')
        # stable indices are on by default (§8.1): the engine declares a budget
        self.engine.max_rule_index.return_value = 2**20 - 1
        # a live engine (NetPlumber): rules always arrive as add_rules
        self.engine.takes_updates.return_value = False
        self.reporter = mock.MagicMock(name='reporter')
        self.aggr = AggregatorService(
            {}, {}, engine=self.engine, reporter=self.reporter
        )


class TestModelFromJson(_AggregatorTestBase):
    """ _model_from_json dispatches on the 'type' field via model_types. """

    def test_known_type_is_reconstructed(self):
        model = PacketFilterModel('fw', ports=['1', '2'])
        rebuilt = self.aggr._model_from_json(model.to_json())
        self.assertEqual(rebuilt.type, 'packet_filter')
        self.assertEqual(rebuilt.node, 'fw')

    def test_unknown_type_raises(self):
        with self.assertRaises(Exception):
            self.aggr._model_from_json({'type': 'bogus_device'})


class TestSyncDiffAddModel(_AggregatorTestBase):
    """ A previously-unseen device model is applied to the engine in full. """

    def test_new_device_calls_engine_and_is_bookkept(self):
        model = PacketFilterModel('fw', ports=['1', '2'])
        self.aggr._sync_diff(model)

        # full apply: tables, wiring and rules all pushed to the backend
        self.engine.add_tables.assert_called_once_with(model)
        self.engine.add_wiring.assert_called_once_with(model)
        self.engine.add_rules.assert_called_once_with(model)

        # bookkeeping: model registered, its (namespaced) ports mapped back
        self.assertIs(self.aggr.models['fw'], model)
        self.assertTrue(self.aggr.port_to_model)
        self.assertIs(self.aggr.port_to_model['fw.1'], model)
        for port in model.ports:
            self.assertIs(self.aggr.port_to_model[port], model)


def _fw(rules, ports=('1', '2')):
    """ A packet filter whose forward_filter holds `rules` (dport values), in
    that order. """
    from rule.rule_model import Forward, Match, Rule, RuleField
    model = PacketFilterModel('fw', ports=list(ports))
    model.tables['fw.forward_filter'] = [
        Rule('fw', 'fw.forward_filter', i, in_ports=['fw.forward_filter_in'],
             match=Match([RuleField('packet.upper.dport', str(d))]),
             actions=[Forward(['fw.forward_filter_accept'])])
        for i, d in enumerate(rules, start=1)]
    return model


class TestSyncStable(_AggregatorTestBase):
    """ INCREMENTAL_PLAN.md §8.1: with stable_indices, a re-sent device reaches
    the engine as the rules that changed; without, nothing changes. """

    def _stable(self):
        self.engine.max_rule_index.return_value = 1000
        return AggregatorService({}, {}, engine=self.engine, reporter=self.reporter,
                                 stable_indices=True)

    def _ff(self, aggr):
        return [(r.idx, r.match[0].value) for r in
                sorted(aggr.models['fw'].tables['fw.forward_filter'], key=lambda r: r.idx)]

    def test_on_by_default(self):
        """ Owner, 2026-10-15: stable indices are the default. """
        self.assertTrue(self.aggr.stable_indices)
        self.assertTrue(build_parser().parse_args([]).stable_indices)

    def test_off_nothing_changes(self):
        """ `--no-stable-indices`: as V5 measured, on the generators' indices. """
        self.assertFalse(build_parser().parse_args(
            ['--no-stable-indices']).stable_indices)
        aggr = AggregatorService({}, {}, engine=self.engine, reporter=self.reporter,
                                 stable_indices=False)
        aggr._sync_diff(_fw([10, 20]))
        aggr._sync_diff(_fw([10, 15, 20]))
        self.engine.insert_rule.assert_not_called()
        self.engine.delete_rule.assert_not_called()
        self.engine.max_rule_index.assert_not_called()

    def test_a_new_table_over_budget_is_refused_untouched(self):
        """ Owner, 2026-10-15: more rules than the engine has index slots is
        refused, before the indexer or the engine is touched. """
        from aggregator.abstract_engine import UpdateRefused
        aggr = self._stable()
        self.engine.max_rule_index.side_effect = \
            lambda table: 2 if table == 'fw.forward_filter' else 1000
        with self.assertRaises(UpdateRefused) as ctx:
            aggr._sync_diff(_fw([10, 20, 30]))
        self.assertIn('fw.forward_filter holds 3 rules', str(ctx.exception))
        self.assertIn('indices up to 2', str(ctx.exception))
        self.engine.add_tables.assert_not_called()
        self.engine.add_rules.assert_not_called()
        self.assertNotIn('fw', aggr.models)
        self.assertIsNone(aggr._indexer.last('fw', 'fw.forward_filter'))
        # a budget of b holds b rules: spaced from 1
        aggr._sync_diff(_fw([10, 20]))
        self.assertEqual(self._ff(aggr), [(1, '10'), (2, '20')])

    def test_a_resend_the_engine_refuses_midway_is_undone(self):
        """ D14: a re-send is all or nothing. The engine refuses an insert
        (before changing anything, §6.2); the deletes and inserts it took for
        the re-send are reverted, and the stored model and the indexer stay
        as they were, so the same re-send can be tried again. """
        from aggregator.abstract_engine import UpdateRefused
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20, 30]))
        before = list(aggr._indexer.last('fw', 'fw.forward_filter'))
        self.engine.reset_mock()
        self.engine.insert_rule.side_effect = [None, UpdateRefused('no'), None, None]
        with self.assertRaises(UpdateRefused):
            aggr._sync_diff(_fw([15, 25, 30]))     # 10, 20 go; 15, 25 come
        deleted = [c.args[2] for c in self.engine.delete_rule.call_args_list]
        inserted = [c.args[0].idx for c in self.engine.insert_rule.call_args_list]
        # 125 and 250 deleted; the first new rule inserted, the second refused;
        # then undone: the inserted rule deleted, 125 and 250 inserted again
        self.assertEqual(deleted[:2], [125, 250])
        self.assertEqual(len(deleted), 3)
        self.assertEqual(sorted(inserted[2:]), [125, 250])
        self.assertEqual(self._ff(aggr), [(125, '10'), (250, '20'), (375, '30')])
        self.assertEqual(aggr._indexer.last('fw', 'fw.forward_filter'), before)
        self.engine.insert_rule.side_effect = None
        aggr._sync_diff(_fw([15, 25, 30]))
        self.assertEqual([v for _i, v in self._ff(aggr)], ['15', '25', '30'])

    def test_a_resend_over_budget_is_refused_untouched(self):
        from aggregator.abstract_engine import UpdateRefused
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20, 30]))
        self.engine.reset_mock()
        self.engine.max_rule_index.return_value = 3
        with self.assertRaises(UpdateRefused):
            aggr._sync_diff(_fw([10, 15, 20, 30]))
        self.engine.insert_rule.assert_not_called()
        self.engine.delete_rule.assert_not_called()
        self.assertEqual(self._ff(aggr), [(125, '10'), (250, '20'), (375, '30')])
        self.assertEqual([i for i, _k in aggr._indexer.last('fw', 'fw.forward_filter')],
                         [125, 250, 375])

    def test_a_replacement_over_budget_is_refused_before_the_removal(self):
        from aggregator.abstract_engine import UpdateRefused
        self.engine.REMOVES_DEVICES = True
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20]))
        self.engine.reset_mock()
        self.engine.max_rule_index.return_value = 2
        with self.assertRaises(UpdateRefused):
            aggr._sync_diff(_fw([10, 15, 20], ports=('1', '2', '3')))
        self.engine.remove_device.assert_not_called()
        self.engine.add_rules.assert_not_called()
        self.assertEqual(self._ff(aggr), [(166, '10'), (332, '20')])

    def test_first_send_is_spaced_and_added_whole(self):
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20, 30]))
        self.engine.add_rules.assert_called_once()
        # budget / (2(n+1)): half the range left for growth
        self.assertEqual(self._ff(aggr), [(125, '10'), (250, '20'), (375, '30')])

    def test_an_insert_is_one_engine_insert(self):
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20, 30]))
        aggr._sync_diff(_fw([10, 15, 20, 30]))
        self.engine.delete_rule.assert_not_called()
        self.engine.insert_rule.assert_called_once()
        rule = self.engine.insert_rule.call_args[0][0]
        self.assertTrue(125 < rule.idx < 250)
        self.assertEqual(aggr.update_stats['inserted'], 1)
        self.assertEqual(self._ff(aggr)[0], (125, '10'))     # the others kept theirs

    def test_a_delete_is_one_engine_delete(self):
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20, 30]))
        aggr._sync_diff(_fw([10, 30]))
        self.engine.delete_rule.assert_called_once_with('fw', 'fw.forward_filter', 250)
        self.engine.insert_rule.assert_not_called()

    def test_a_modify_deletes_before_it_inserts(self):
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20, 30]))
        self.engine.reset_mock()
        aggr._sync_diff(_fw([10, 21, 30]))
        names = [c[0] for c in self.engine.mock_calls
                 if c[0] in ('delete_rule', 'insert_rule')]
        self.assertEqual(names, ['delete_rule', 'insert_rule'])

    def test_what_the_engine_cannot_take_is_refused_untouched(self):
        """ A structural change on an engine that only empties a removed
        device (VeriFlow-FR, APKeep). """
        from aggregator.abstract_engine import UpdateRefused
        self.engine.REMOVES_DEVICES = False
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20]))
        self.engine.reset_mock()
        with self.assertRaises(UpdateRefused):
            aggr._sync_diff(_fw([10, 15, 20], ports=('1', '2', '3')))
        self.engine.insert_rule.assert_not_called()
        self.engine.delete_rule.assert_not_called()
        self.engine.remove_device.assert_not_called()
        # the stored model and its indices are unchanged by a refusal
        self.assertEqual(self._ff(aggr), [(166, '10'), (332, '20')])

    def _linked(self, aggr):
        """ fw built and linked to a switch on fw.1 and fw.2. """
        from devices.switch import SwitchModel
        aggr._sync_diff(_fw([10, 20]))
        aggr._sync_diff(SwitchModel('sw', ports=['1', '2']))
        for link in (('sw.1', 'fw.1'), ('fw.2', 'sw.2')):
            aggr.links.setdefault(link[0], []).append(link[1])
        self.engine.reset_mock()

    def test_a_structural_change_replaces_the_device(self):
        """ INCREMENTAL_PLAN.md §8.2, D-R6: removed with its links, added as
        new, its links added again -- one update. """
        self.engine.REMOVES_DEVICES = True
        aggr = self._stable()
        self._linked(aggr)
        old = aggr.models['fw']
        aggr._sync_diff(_fw([10, 15, 20], ports=('1', '2', '3')))
        self.engine.remove_device.assert_called_once()
        self.assertIs(self.engine.remove_device.call_args[0][0], old)
        self.assertEqual(sorted(self.engine.remove_device.call_args[0][1]),
                         [('fw.2_egress', 'sw.2'), ('sw.1', 'fw.1_ingress')])
        names = [c[0] for c in self.engine.mock_calls
                 if c[0] in ('remove_device', 'add_rules', 'add_link')]
        self.assertEqual(names, ['remove_device', 'add_rules', 'add_link', 'add_link'])
        self.engine.insert_rule.assert_not_called()
        self.assertIsNot(aggr.models['fw'], old)
        self.assertIn('fw.3', aggr.port_to_model)
        self.assertEqual(aggr.links, {'sw.1': ['fw.1'], 'fw.2': ['sw.2']})
        # spaced afresh, as a new device
        self.assertEqual(self._ff(aggr), [(125, '10'), (250, '15'), (375, '20')])
        self.assertEqual(aggr.update_stats['replaced'], 'has other ports or wiring')

    def test_a_replacement_keeps_the_commanded_routing_table(self):
        """ A pf's routing table comes from the control plane and arrives
        EMPTY in a configuration re-send: the new device keeps its rules, at
        the sender's indices, and the next re-send still diffs against them. """
        from rule.rule_model import Rule, Match, RuleField
        self.engine.REMOVES_DEVICES = True
        aggr = self._stable()
        aggr._sync_diff(_fw([10, 20]))
        route = Rule('fw', 'fw.routing', 7,
                     match=Match([RuleField('packet.ipv6.destination', '2001:db8::/32')]))
        aggr._sync_diff(SwitchCommand('fw', 'add_rules', [route]))
        held = [r.idx for r in aggr.models['fw'].tables['fw.routing']]
        aggr._sync_diff(_fw([10, 20], ports=('1', '2', '3')))
        self.engine.remove_device.assert_called_once()
        self.assertEqual([r.idx for r in aggr.models['fw'].tables['fw.routing']], held)
        self.assertIn(('fw', 'fw.routing'), aggr._commanded)
        self.engine.reset_mock()
        aggr._sync_diff(_fw([10, 20], ports=('1', '2', '3')))
        self.engine.delete_rule.assert_not_called()
        self.engine.remove_device.assert_not_called()

    def test_a_dropped_port_with_a_link_is_refused_untouched(self):
        from aggregator.abstract_engine import UpdateRefused
        self.engine.REMOVES_DEVICES = True
        aggr = self._stable()
        self._linked(aggr)
        old = aggr.models['fw']
        with self.assertRaises(UpdateRefused) as ctx:
            aggr._sync_diff(_fw([10, 20], ports=('1', '3')))
        self.assertIn('fw.2 -> sw.2', str(ctx.exception))
        self.engine.remove_device.assert_not_called()
        self.assertIs(aggr.models['fw'], old)

    def test_a_switch_filled_by_commands_is_re_sent_as_its_difference(self):
        from rule.rule_model import Rule, Match, RuleField
        from devices.switch import SwitchModel
        aggr = self._stable()
        aggr._sync_diff(SwitchModel('s1', ports=['1']))
        rules = [Rule('s1', 's1.1', i, match=Match([RuleField('packet.upper.dport', str(i))]))
                 for i in (1, 2, 3)]
        aggr._sync_diff(SwitchCommand('s1', 'add_rules', rules))
        self.engine.reset_mock()
        whole = SwitchModel('s1', ports=['1'])
        whole.tables['s1.1'] = [rules[0], rules[2]]          # rule 2 removed
        aggr._sync_diff(whole)
        # the engine held the commanded indices: one delete, nothing re-added
        self.engine.delete_rule.assert_called_once_with('s1', 's1.1', 2)
        self.engine.insert_rule.assert_not_called()

    def test_a_switch_command_keeps_its_own_indices(self):
        from rule.rule_model import Rule
        aggr = self._stable()
        from devices.switch import SwitchModel
        aggr._sync_diff(SwitchModel('s1', ports=['1']))
        self.engine.reset_mock()
        aggr._sync_diff(SwitchCommand('s1', 'add_rules', [Rule('s1', 's1.1', 7)]))
        self.engine.insert_rule.assert_not_called()
        self.engine.add_rules.assert_called_once()


class TestSyncDiffCommands(_AggregatorTestBase):
    """ Control-plane commands take the short-circuit branches in _sync_diff. """

    def test_switch_command_dispatches_to_device(self):
        device = mock.MagicMock(name='device')
        # avoid the trailing _add_model re-add touching real attributes
        device.node = 'sw'
        self.aggr.models['sw'] = device

        from rule.rule_model import Rule
        rule = Rule('sw', 'sw.1', 0)
        cmd = SwitchCommand('sw', 'add_rule', [rule])
        self.aggr._sync_diff(cmd)

        device.add_rule.assert_called_once_with([rule])

    def test_switch_command_unknown_node_is_ignored(self):
        from rule.rule_model import Rule
        cmd = SwitchCommand('ghost', 'add_rule', [Rule('ghost', 'ghost.1', 0)])
        self.aggr._sync_diff(cmd)
        # nothing applied to the engine for an unknown datapath
        self.engine.add_tables.assert_not_called()

    def test_add_slice_forwards_to_engine(self):
        slc = Slice(1)
        cmd = SlicingCommand('add_slice', slicem=slc)
        self.aggr._sync_diff(cmd)
        self.engine.add_slice.assert_called_once_with(slc)
        # a command must not be mistaken for a device model
        self.assertNotIn('add_slice', self.aggr.models)

    def test_del_slice_forwards_to_engine(self):
        slc = Slice(1)
        cmd = SlicingCommand('del_slice', slicem=slc)
        self.aggr._sync_diff(cmd)
        self.engine.del_slice.assert_called_once_with(slc)


class TestHandlerDispatch(_AggregatorTestBase):
    """ _handler pulls JSON tasks off the queue and dispatches by 'type'. """

    def _run_handler_with(self, *events):
        """ Enqueue events (dicts -> JSON), ending with a stop, run the loop. """
        for ev in events:
            self.aggr.queue.put(json.dumps(ev))
        self.aggr.queue.put(json.dumps({'type': 'stop'}))
        self.aggr._handler()

    def test_stop_sets_flag_and_stops_engine(self):
        self._run_handler_with()
        self.assertTrue(self.aggr.stop)
        self.engine.stop.assert_called_once_with()

    def test_empty_data_is_ignored(self):
        # an empty frame must not crash the worker nor reach the engine
        self.aggr.queue.put('')
        self.aggr.queue.put(json.dumps({'type': 'stop'}))
        self.aggr._handler()
        self.assertTrue(self.aggr.stop)

    def test_check_compliance_forwards_rules(self):
        self._run_handler_with({'type': 'check_compliance', 'rules': {}})
        self.engine.check_compliance.assert_called_once_with({})

    def test_check_anomalies_passes_flags(self):
        self._run_handler_with({'type': 'check_anomalies', 'use_reach': True})
        self.engine.check_anomalies.assert_called_once_with(
            use_shadow=False, use_reach=True, use_general=False
        )

    def test_an_unguarded_refusal_is_kept_and_logged_on_its_own_line(self):
        """ A device of a from-zero build carries no barrier: its failure is
        kept for the build's driver, and a refusal gets a line `cell_run.py`
        reads (owner, 2026-10-15). """
        self.engine.max_rule_index.return_value = 1
        with self.assertLogs('Aggregator', level='ERROR') as logs:
            self._run_handler_with(_fw([10, 20]).to_json())
        self.assertEqual(len(self.aggr.unguarded_failures), 1)
        self.assertTrue(self.aggr.unguarded_failures[0].startswith('UpdateRefused: '))
        self.assertTrue(any('worker: REFUSED, with no one waiting: ' in line
                            for line in logs.output))
        self.assertNotIn('fw', self.aggr.models)

    def test_device_model_is_synced(self):
        model = PacketFilterModel('fw', ports=['1'])
        self._run_handler_with(model.to_json())
        # the model travelled queue -> _model_from_json -> _sync_diff -> engine
        self.engine.add_tables.assert_called_once()
        self.assertIn('fw', self.aggr.models)


class TestDumpAggregator(_AggregatorTestBase):
    """ _dump_aggregator serialises the engine's id maps to fave.json.

    The rule-id encoding is coupled to the adapter: the adapter packs a rule
    key as ``(t_idx << 32) + (r_idx << 12) + n_idx`` and the dump reverses the
    node nibble with ``key >> 12``.  This test pins that contract.
    """

    def test_id_maps_are_inverted_and_rule_key_shifted(self):
        self.engine.mapping.to_json.return_value = {'length': 0}
        self.engine.tables = {'fw.1': 0x2a}
        self.engine.generators = {'gen': (0x3, 0x300, 'm')}
        self.engine.probes = {'pr': (0x4, 0x400)}
        self.engine.ports = {'fw.1': 0x10001}
        # one rule key -> two NetPlumber node ids
        rule_key = (1 << 32) + (5 << 12) + 7
        self.engine.rule_ids = {rule_key: [111, 222]}
        self.aggr.links = {}

        with tempfile.TemporaryDirectory() as odir:
            self.aggr._dump_aggregator(odir)
            with open(os.path.join(odir, 'fave.json')) as ofile:
                dump = json.load(ofile)

        self.assertEqual(dump['id_to_table'], {'42': 'fw.1'})
        self.assertEqual(dump['id_to_generator'], {'768': 'gen'})
        self.assertEqual(dump['id_to_probe'], {'1024': 'pr'})
        self.assertEqual(dump['id_to_port'], {'65537': 'fw.1'})
        # both node ids resolve to the same shifted rule key
        shifted = rule_key >> 12
        self.assertEqual(dump['id_to_rule'], {'111': shifted, '222': shifted})

    def test_an_engine_without_an_id_map_writes_no_fave_json(self):
        """ TODO item 57: fave.json is NetPlumber's; every other engine raised
        AttributeError here. """
        self.engine.mapping = None
        with tempfile.TemporaryDirectory() as odir:
            self.aggr._dump_aggregator(odir)
            self.assertFalse(os.path.exists(os.path.join(odir, 'fave.json')))

    def test_a_failed_dump_still_releases_the_dumpers_lock(self):
        """ TODO item 58: the lock used to outlive a failed dump, and the next
        run's `misc/await_fave.py` waited on it forever. """
        self.engine.dump_flow_trees.side_effect = RuntimeError('boom')
        with tempfile.TemporaryDirectory() as odir:
            lock = os.path.join(odir, '.lock')
            open(lock, 'w').close()
            with self.assertRaises(RuntimeError):
                self.aggr._dispatch({'type': 'dump', 'dir': odir, 'fave': False,
                                     'flows': False, 'network': False,
                                     'pipes': False, 'trees': True,
                                     'simple': False})
            self.assertFalse(os.path.exists(lock))


if __name__ == '__main__':
    unittest.main()
