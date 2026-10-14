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

""" The aggregator service's request paths that `test_aggregator.py` leaves
open: report/dump/compliance dispatch, topology commands (links, generators,
probes), declared-LPM validation, barrier release on success and on failure,
the abandoned-queue drain, and `run()`'s socket loop end to end.

Pure Python, like `test_aggregator.py`: the engine is a recording `MagicMock`
and the reporter a stub, injected through the constructor's seams. `run()` is
driven over a UNIX socket in a temporary directory, never a TCP port, and the
barrier directory is redirected there too, so nothing touches /dev/shm.
"""

# pylint: disable=protected-access

import io
import json
import logging
import os
import socket
import tempfile
import threading
import time
import types
import unittest

from contextlib import redirect_stderr
from unittest import mock

import aggregator.aggregator_service as aggregator_service
from aggregator.aggregator_abstract import TRACE
from aggregator.aggregator_service import AggregatorService
from devices.abstract_device import LPM, TableSemanticsError
from devices.generator import GeneratorModel
from devices.packet_filter import PacketFilterModel
from devices.probe import ProbeModel
from devices.switch import SwitchCommand, SwitchModel
from rule.rule_model import Forward, Match, Rule, RuleField
from topology.topology import GeneratorsModel, LinksModel, TopologyCommand
from util import barrier
from util.aggregator_utils import connect_to_fave, fave_sendmsg


class _Base(unittest.TestCase):
    """ A service over a recording engine and a stub reporter, with the barrier
    directory redirected into a private temporary directory. """

    def setUp(self):
        logging.getLogger('Aggregator').setLevel(logging.WARNING)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(barrier, 'BARRIER_DIR', self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.engine = mock.MagicMock(name='engine')
        self.engine.asyncore_socks = {}
        self.engine.links = {}
        # global_port: an injective stand-in for the adapter's port numbering
        # (first come, first numbered), so the bookkeeping can be checked.
        self.port_numbers = {}
        self.engine.global_port.side_effect = lambda port: \
            self.port_numbers.setdefault(port, 0x100 + len(self.port_numbers))
        self.reporter = mock.MagicMock(name='reporter')
        self.aggr = AggregatorService(
            {}, {}, engine=self.engine, reporter=self.reporter
        )

    def _barrier_state(self, path):
        with open(path, encoding='utf-8') as bfile:
            return json.load(bfile)


class TestPrintAggregator(_Base):
    """ print_aggregator dumps the engine's id maps to stderr, labelled. """

    def test_every_map_is_printed_under_its_label(self):
        self.engine.configure_mock(
            mapping='MAP', tables={'fw.1': 1}, ports={'fw.1': 2},
            rule_ids={3: [4]}, links={5: [6]}, generators={'g': 7},
            probes={'p': 8})
        err = io.StringIO()
        with redirect_stderr(err):
            self.aggr.print_aggregator()
        text = err.getvalue()
        for label in ('Aggregator:', 'tables:', 'ports:', 'rule ids:',
                      'links:', 'generators:', 'probes:'):
            self.assertIn(label, text)
        self.assertIn("{'fw.1': 1}", text)
        self.assertIn("{'g': 7}", text)


class TestDispatchRequests(_Base):
    """ _dispatch's non-model request types and the task type it reports. """

    def test_report_drains_then_dumps_then_advances_both_windows(self):
        """ The tailer must catch up BEFORE rendering (else a partial verdict),
        and both windows move only after the report is written. """
        task = self.aggr._dispatch({'type': 'report', 'file': 'out.md'})
        self.assertEqual(task, 'report')
        self.assertEqual(
            [c[0] for c in self.reporter.method_calls],
            ['drain', 'dump_report', 'mark_compliance', 'mark_anomalies']
        )
        self.reporter.dump_report.assert_called_once_with('out.md')

    def test_check_compliance_rebuilds_rule_fields(self):
        """ The wire format's JSON fields arrive at the engine as RuleField
        objects, grouped per destination, with the negation flag intact. """
        field = RuleField('packet.upper.dport', '80').to_json()
        task = self.aggr._dispatch({
            'type': 'check_compliance',
            'rules': {'probe.b': [['source.a', True, [field]],
                                  ['source.c', False, []]]}
        })
        self.assertEqual(task, 'check_compliance')
        (rules,), _ = self.engine.check_compliance.call_args
        self.assertEqual(list(rules), ['probe.b'])
        (src1, neg1, cond1), (src2, neg2, cond2) = rules['probe.b']
        self.assertEqual((src1, neg1, src2, neg2), ('source.a', True, 'source.c', False))
        self.assertEqual(len(cond1), 1)
        self.assertIsInstance(cond1[0], RuleField)
        self.assertEqual((cond1[0].name, cond1[0].value), ('packet.upper.dport', '80'))
        self.assertEqual(cond2, [])

    def test_check_anomalies_defaults_every_flag_off(self):
        self.assertEqual(
            self.aggr._dispatch({'type': 'check_anomalies'}), 'check_anomalies')
        self.engine.check_anomalies.assert_called_once_with(
            use_shadow=False, use_reach=False, use_general=False)

    def test_dump_runs_only_the_requested_parts_and_releases_the_lock(self):
        odir = os.path.join(self.tmp.name, 'dump')
        os.makedirs(odir)
        request = {
            'type': 'dump', 'dir': odir, 'fave': False, 'flows': True,
            'network': False, 'pipes': True, 'trees': True, 'simple': True
        }
        task = self.aggr._dispatch(request)
        # the task type names every flag the request carried
        self.assertTrue(task.startswith('dump '))
        self.assertEqual(
            set(task[len('dump '):].split(',')),
            {'fave', 'flows', 'network', 'pipes', 'trees', 'simple'})
        self.engine.dump_flows.assert_called_once_with(odir)
        self.engine.dump_pipes.assert_called_once_with(odir)
        self.engine.dump_flow_trees.assert_called_once_with(odir, True)
        self.engine.dump_plumbing_network.assert_not_called()

    @unittest.expectedFailure
    def test_dump_removes_its_lock_file(self):
        """ BUG, pinned as expected-failure: the dump is announced to the
        waiter by releasing `<dir>/.lock` through `PreLockedFileLock`. Under the
        pinned filelock (3.29.4) that class's `_lock_file_fd` assignment no
        longer reaches the lock's context, so `is_locked` is False, `release()`
        is a no-op and the file -- and an open fd -- survive. """
        odir = os.path.join(self.tmp.name, 'dump')
        os.makedirs(odir)
        self.aggr._dispatch({
            'type': 'dump', 'dir': odir, 'fave': False, 'flows': False,
            'network': False, 'pipes': False, 'trees': False})
        self.assertFalse(os.path.exists(os.path.join(odir, '.lock')))

    def test_dump_with_fave_writes_the_aggregator_state(self):
        odir = os.path.join(self.tmp.name, 'dump')
        self.engine.mapping.to_json.return_value = {'length': 0}
        self.engine.tables = {}
        self.engine.rule_ids = {}
        self.engine.generators = {}
        self.engine.probes = {}
        self.engine.ports = {}
        self.aggr.links = {'a.1': ['b.1']}
        self.aggr._dispatch({
            'type': 'dump', 'dir': odir, 'fave': True, 'flows': False,
            'network': True, 'pipes': False, 'trees': False
        })
        self.engine.dump_plumbing_network.assert_called_once_with(odir)
        with open(os.path.join(odir, 'fave.json'), encoding='utf-8') as ofile:
            dump = json.load(ofile)
        self.assertEqual(dump['links'], [['a.1', ['b.1']]])
        self.assertEqual(dump['mapping'], {'length': 0})

    def test_topology_command_reports_the_wrapped_model_type(self):
        gen = GeneratorModel('src')
        task = self.aggr._dispatch(TopologyCommand('src', 'add', model=gen).to_json())
        self.assertEqual(task, 'generator')
        self.engine.add_generator.assert_called_once()

    def test_device_model_reports_its_own_type(self):
        task = self.aggr._dispatch(PacketFilterModel('fw', ports=['1']).to_json())
        self.assertEqual(task, 'packet_filter')


class TestLinks(_Base):
    """ Link commands: port names resolved through the owning model, engine
    port numbers taken from `global_port`, bulk links batched. """

    def setUp(self):
        super().setUp()
        for node in ('a', 'b'):
            self.aggr._sync_diff(PacketFilterModel(node, ports=['1', '2']))
        self.engine.reset_mock()

    def _links(self, command, links):
        self.aggr._sync_diff(TopologyCommand(
            'links', command, model=LinksModel(links)))

    def test_single_link_is_added_immediately(self):
        self._links('add', [('a.1', 'b.1', False)])
        # a packet filter's outer ports map to its egress/ingress stages
        self.engine.add_link.assert_called_once_with('a.1_egress', 'b.1_ingress')
        self.engine.add_links_bulk.assert_not_called()
        self.assertEqual(self.aggr.links, {'a.1': ['b.1']})
        num = self.port_numbers
        self.assertEqual(self.engine.links, {num['a.1_egress']: [num['b.1_ingress']]})

    def test_bulk_links_go_in_one_batch_without_dynamic_dispatch(self):
        self._links('add', [('a.1', 'b.1', True), ('b.2', 'a.2', True)])
        self.engine.add_link.assert_not_called()
        self.engine.add_links_bulk.assert_called_once_with(
            [('a.1_egress', 'b.1_ingress'), ('b.2_egress', 'a.2_ingress')],
            use_dynamic=False)
        self.assertEqual(self.aggr.links, {'a.1': ['b.1'], 'b.2': ['a.2']})

    def test_bulk_links_use_dynamic_dispatch_only_with_live_async_sockets(self):
        """ `_has_asyncore_socks`: every registered async socket must exist. """
        self.engine.asyncore_socks = {('h', 1): object()}
        self._links('add', [('a.1', 'b.1', True)])
        self.assertEqual(
            self.engine.add_links_bulk.call_args[1], {'use_dynamic': True})

        self.engine.asyncore_socks = {('h', 1): None}
        self._links('add', [('a.2', 'b.2', True)])
        self.assertEqual(
            self.engine.add_links_bulk.call_args[1], {'use_dynamic': False})

    def test_delete_removes_the_link_and_forgets_an_emptied_source(self):
        with self.assertLogs('Aggregator', level=logging.DEBUG) as logs:
            self._links('add', [('a.1', 'b.1', False), ('a.1', 'b.2', True)])
            self._links('del', [('a.1', 'b.1', False)])
        text = '\n'.join(logs.output)
        self.assertIn('add link to netplumber from a.1:', text)
        self.assertIn('as bulk', text)
        self.assertIn('worker: add all bulk links', text)
        self.assertIn('remove link from netplumber from a.1 to b.1', text)
        num = self.port_numbers
        self.engine.remove_link.assert_called_once_with(
            num['a.1_egress'], num['b.1_ingress'])
        self.assertEqual(self.aggr.links, {'a.1': ['b.2']})
        self._links('del', [('a.1', 'b.2', True)])
        self.assertNotIn('a.1', self.aggr.links)

    def test_a_link_to_an_unknown_port_raises(self):
        with redirect_stderr(io.StringIO()), \
                mock.patch('pprint.pprint'):
            with self.assertRaises(KeyError):
                self._links('add', [('a.1', 'nowhere.1', False)])
        self.engine.add_link.assert_not_called()


class TestGeneratorsAndProbes(_Base):
    """ Generator/probe commands register their ports and reach the engine;
    deletion goes by node name. """

    def test_generator_add_registers_its_port(self):
        gen = GeneratorModel('src')
        self.aggr._sync_diff(TopologyCommand('src', 'add', model=gen))
        self.engine.add_generator.assert_called_once_with(gen)
        self.assertIs(self.aggr.port_to_model['src.1'], gen)
        # a generator is not a device model
        self.assertNotIn('src', self.aggr.models)

    def test_generator_delete_goes_by_node(self):
        self.aggr._sync_diff(TopologyCommand('src', 'del', mtype='generator'))
        self.engine.delete_generator.assert_called_once_with('src')

    def test_generators_bulk_registers_every_port_in_one_call(self):
        gens = [GeneratorModel('s1'), GeneratorModel('s2')]
        self.aggr._sync_diff(TopologyCommand(
            'gens', 'add', model=GeneratorsModel(gens)))
        self.engine.add_generators_bulk.assert_called_once_with(
            gens, use_dynamic=False)
        self.assertIs(self.aggr.port_to_model['s2.1'], gens[1])

    def test_generators_delete_is_a_no_op(self):
        """ Not implemented (commented TODO in the service): nothing reaches
        the engine and nothing raises. """
        self.aggr._sync_diff(TopologyCommand('gens', 'del', mtype='generators'))
        self.assertEqual(self.engine.method_calls, [])

    def test_probe_add_rewrites_test_path_ports_to_ingress_ports(self):
        """ Port pathlets are rewritten through the OWNING model's
        ingress_port; other pathlets are kept as they are. """
        owner = mock.MagicMock(name='owner')
        owner.ingress_port.side_effect = lambda p: p + '_in'
        self.aggr.port_to_model.update({'fw.1': owner, 'fw.2': owner, 'fw.3': owner})
        probe = ProbeModel('dst', 'universal', test_path=[
            '.*(port=fw.1)', '(port in (fw.2,fw.3))', '.*(port in (fw.1))$',
            '.*(table=fw.t)'
        ])
        self.aggr._sync_diff(TopologyCommand('dst', 'add', model=probe))

        self.engine.add_probe.assert_called_once_with(probe)
        self.assertIs(self.aggr.port_to_model['dst.1'], probe)
        self.assertEqual(probe.test_path.pathlets, [
            '.*(port=fw.1_in)', '(port in (fw.2_in,fw.3_in))',
            '.*(port in (fw.1_in))$', '.*(table=fw.t)'
        ])

    def test_probe_without_test_path_is_left_alone(self):
        probe = ProbeModel('dst', 'universal')
        probe.test_path = None
        self.aggr._sync_diff(TopologyCommand('dst', 'add', model=probe))
        self.assertIsNone(probe.test_path)
        self.engine.add_probe.assert_called_once_with(probe)

    def test_probe_delete_goes_by_node(self):
        self.aggr._sync_diff(TopologyCommand('dst', 'del', mtype='probe'))
        self.engine.delete_probe.assert_called_once_with('dst')

    def test_an_unknown_topology_type_is_ignored(self):
        self.aggr._sync_diff(TopologyCommand('x', 'add', mtype='hologram'))
        self.assertEqual(self.engine.method_calls, [])
        self.assertEqual(self.aggr.models, {})

    def test_a_wrapped_device_is_applied_like_a_bare_one(self):
        model = PacketFilterModel('fw', ports=['1'])
        self.aggr._sync_diff(TopologyCommand('fw', 'add', model=model))
        self.engine.add_tables.assert_called_once_with(model)
        self.assertIs(self.aggr.models['fw'], model)

    @unittest.expectedFailure
    def test_a_generator_delete_from_the_wire_reaches_the_engine(self):
        """ BUG, pinned as expected-failure: `topology.py -c del` sends a
        TopologyCommand WITHOUT a model, and `_dispatch` reads
        `model.model.type` for the task name before `_sync_diff` ever sees it,
        so every non-link delete raises AttributeError and the
        `delete_generator` / `delete_probe` branches are unreachable from the
        wire. """
        self.aggr._dispatch(
            TopologyCommand('src', 'del', mtype='generator').to_json())
        self.engine.delete_generator.assert_called_once_with('src')


class TestSwitchUpdatesAndDeclaredLpm(_Base):
    """ An incremental switch update sends only the delta to the engine, and a
    table declared longest-prefix-match is validated ACROSS batches. """

    @staticmethod
    def _rule(idx, prefix, out):
        return Rule('sw', 'sw.1', idx,
                    match=Match([RuleField('packet.ipv4.destination', prefix)]),
                    actions=[Forward([out])] if out else [])

    def _switch(self, *rules, lpm=False):
        switch = SwitchModel('sw', ports=['1', '2'], rules=list(rules))
        if lpm:
            switch.set_table_semantics('sw.1', LPM)
        self.aggr._dispatch(switch.to_json())
        self.engine.reset_mock()

    def test_add_rules_sends_only_the_new_rule_and_folds_it_in(self):
        self._switch(self._rule(0, '10.0.0.0/8', 'sw.2'))
        new = self._rule(1, '10.1.0.0/16', 'sw.2')
        self.aggr._dispatch(SwitchCommand('sw', 'add_rules', [new]).to_json())

        (delta,), _ = self.engine.add_rules.call_args
        self.assertEqual([r.idx for r in delta.tables['sw.1']], [1])
        stored = self.aggr.models['sw']
        self.assertEqual([r.idx for r in stored.tables['sw.1']], [0, 1])
        # the add buffer was consumed, so the next diff starts clean
        self.assertEqual(stored._adds, {'sw.1': []})

    def test_the_delta_keeps_the_table_declaration(self):
        self._switch(self._rule(0, '10.0.0.0/8', 'sw.2'), lpm=True)
        new = self._rule(1, '10.1.0.0/16', 'sw.2')
        self.aggr._dispatch(SwitchCommand('sw', 'add_rules', [new]).to_json())
        (delta,), _ = self.engine.add_tables.call_args
        self.assertEqual(delta.semantics_of('sw.1'), LPM)

    def test_a_collision_across_batches_is_refused_before_the_engine(self):
        self._switch(self._rule(0, '10.0.0.0/8', 'sw.2'), lpm=True)
        clash = self._rule(1, '10.0.0.0/8', None)      # same prefix, drops
        with self.assertRaises(TableSemanticsError):
            self.aggr._dispatch(SwitchCommand('sw', 'add_rules', [clash]).to_json())
        self.engine.add_tables.assert_not_called()
        self.engine.add_rules.assert_not_called()

    def test_an_lpm_table_with_a_non_destination_match_is_refused(self):
        bad = Rule('sw', 'sw.1', 0,
                   match=Match([RuleField('packet.upper.dport', '80')]),
                   actions=[Forward(['sw.2'])])
        switch = SwitchModel('sw', ports=['1', '2'], rules=[bad])
        switch.set_table_semantics('sw.1', LPM)
        with self.assertRaises(TableSemanticsError):
            self.aggr._sync_diff(switch)
        self.assertNotIn('sw', self.aggr.models)

    def test_a_model_without_declarations_is_not_validated(self):
        # no `semantics_of` at all: returns before touching the index
        self.aggr._validate_declared_tables(types.SimpleNamespace(node='x'))
        self.assertEqual(self.aggr._lpm_index, {})


class TestDeleteModel(_Base):
    """ _delete_model is the inverse of _add_model, ports included. """

    def test_delete_undoes_the_engine_state_and_the_port_map(self):
        model = PacketFilterModel('fw', ports=['1', '2'])
        with self.assertLogs('Aggregator', level=logging.DEBUG) as logs:
            self.aggr._add_model(model)
            self.assertTrue(self.aggr.port_to_model)
            self.aggr._delete_model(model)
        self.assertIn('worker: delete packet_filter: fw', logs.output[-1])
        self.engine.delete_rules.assert_called_once_with(model)
        self.engine.delete_wiring.assert_called_once_with(model)
        self.engine.delete_tables.assert_called_once_with(model)
        self.assertEqual(self.aggr.port_to_model, {})


class TestHandlerBarriers(_Base):
    """ _handler releases every request's barrier -- with the error text when
    handling raised -- and fails the barriers of requests still queued at stop
    (TODO.md item 1r). """

    def _enqueue(self, *messages):
        for msg in messages:
            self.aggr.queue.put(msg if isinstance(msg, str) else json.dumps(msg))

    def test_success_and_failure_both_release(self):
        ok = barrier.arm(self.tmp.name)
        bad = barrier.arm(self.tmp.name)
        self.engine.check_anomalies.side_effect = RuntimeError('engine on fire')
        self._enqueue(
            {'type': 'check_compliance', 'rules': {}, 'barrier': ok},
            {'type': 'check_anomalies', 'barrier': bad},
            {'type': 'stop'})
        with self.assertLogs('Aggregator', level='ERROR'):
            self.aggr._handler()

        self.assertEqual(self._barrier_state(ok), {'state': 'done', 'error': None})
        self.assertEqual(self._barrier_state(bad), {
            'state': 'done', 'error': 'RuntimeError: engine on fire'})
        # the worker survived the failure and went on to the stop
        self.assertTrue(self.aggr.stop)
        self.engine.stop.assert_called_once_with()

    def test_an_unknown_model_type_fails_its_barrier(self):
        path = barrier.arm(self.tmp.name)
        self._enqueue({'type': 'bogus', 'barrier': path}, {'type': 'stop'})
        with self.assertLogs('Aggregator', level='ERROR'):
            self.aggr._handler()
        state = self._barrier_state(path)
        self.assertIn('model type not implemented: bogus', state['error'])

    def test_requests_queued_behind_a_stop_are_failed_not_dropped(self):
        behind = barrier.arm(self.tmp.name)
        self._enqueue(
            {'type': 'stop'},
            {'type': 'check_compliance', 'rules': {}, 'barrier': behind},
            {'type': 'check_anomalies'},       # no barrier: just discarded
            'not json',                        # unparseable: just discarded
            '')
        with self.assertLogs('Aggregator', level='WARNING') as logs:
            self.aggr._handler()

        self.engine.check_compliance.assert_not_called()
        self.engine.check_anomalies.assert_not_called()
        self.assertEqual(self._barrier_state(behind), {
            'state': 'done',
            'error': 'the aggregator stopped before handling this request'})
        self.assertTrue(any('abandoning queued check_compliance' in line
                            for line in logs.output))
        # every get() was matched by task_done(), so run()'s join can finish
        self.assertEqual(self.aggr.queue.unfinished_tasks, 0)

    def test_unparseable_data_ends_the_worker(self):
        """ A malformed frame is fatal to the worker (logged at FATAL), and the
        frame is still marked done so `queue.join` cannot hang on it. """
        self._enqueue('{broken', {'type': 'stop'})
        with self.assertLogs('Aggregator', level='CRITICAL') as logs:
            self.aggr._handler()
        self.assertIn('could not parse data: {broken', logs.output[0])
        self.assertFalse(self.aggr.stop)
        self.engine.stop.assert_not_called()
        self.assertEqual(self.aggr.queue.unfinished_tasks, 1)   # the stop

    def test_verbose_logging_reports_each_task(self):
        """ The DEBUG/TRACE/INFO branches: each task is logged with its type. """
        self._enqueue('', {'type': 'check_anomalies'}, {'type': 'stop'})
        with self.assertLogs('Aggregator', level=TRACE) as logs:
            self.aggr._handler()
        text = '\n'.join(logs.output)
        self.assertIn('worker: ignoring empty data', text)
        self.assertIn('worker: parsed data', text)
        self.assertIn('worker: completed task check_anomalies in', text)
        self.assertIn('worker: completed task stop in', text)
        self.assertIn('worker: stop handler after', text)


class _QuickSocket(socket.socket):
    """ The service's listening socket, with its 2 s accept timeout cut to a
    few milliseconds so a stop is noticed at once. Behaviour is otherwise the
    real socket's. """

    def settimeout(self, value):
        super().settimeout(min(value, 0.02) if value else value)


class TestRunOverUnixSocket(_Base):
    """ run(): bind, publish the barrier owner, receive framed messages into
    the queue, stop on request, then withdraw the owner and stop the reporter.
    Driven end to end through a real UNIX socket in a temporary directory. """

    def setUp(self):
        super().setUp()
        fake_socket_module = types.SimpleNamespace(
            socket=_QuickSocket, AF_UNIX=socket.AF_UNIX, AF_INET=socket.AF_INET,
            SOCK_STREAM=socket.SOCK_STREAM, timeout=socket.timeout,
            error=socket.error)
        patcher = mock.patch.object(aggregator_service, 'socket', fake_socket_module)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sock_path = os.path.join(self.tmp.name, 'aggr.socket')
        self.owner = barrier.owner_path(self.tmp.name)

    def _send(self, message):
        conn = connect_to_fave(self.sock_path)
        try:
            fave_sendmsg(conn, json.dumps(message))
        finally:
            conn.close()

    def _wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'timed out')
            time.sleep(0.005)

    def test_requests_are_handled_in_order_and_shutdown_is_clean(self):
        logging.getLogger('Aggregator').setLevel(logging.DEBUG)
        server = threading.Thread(
            target=self.aggr.run, args=(self.sock_path,), daemon=True)
        with self.assertLogs('Aggregator', level=logging.DEBUG) as logs:
            server.start()
            self._wait_for(lambda: os.path.exists(self.owner))
            self.reporter.start.assert_called_once_with()

            self._send(PacketFilterModel('fw', ports=['1']).to_json())
            guard = barrier.arm(self.tmp.name)
            self._send({'type': 'check_compliance', 'rules': {}, 'barrier': guard})
            barrier.wait(guard, directory=self.tmp.name, poll=0.005)
            # FIFO: the model was applied before the check answered
            self.engine.add_tables.assert_called_once()
            self.engine.check_compliance.assert_called_once_with({})

            stop_guard = barrier.arm(self.tmp.name)
            self._send({'type': 'stop', 'barrier': stop_guard})
            barrier.wait(stop_guard, directory=self.tmp.name, poll=0.005)
            server.join(5)

        self.assertFalse(server.is_alive())
        self.assertTrue(self.aggr.stop)
        self.engine.stop.assert_called_once_with()
        self.reporter.stop.assert_called_once_with()
        # the registration is withdrawn only after the queue drained
        self.assertFalse(os.path.exists(self.owner))
        text = '\n'.join(logs.output)
        self.assertIn('master: open and bind unix socket', text)
        self.assertIn('master: listening timed out, continue loop...', text)
        self.assertIn('master: enqueued data', text)
        self.assertIn('master: finished run', text)


if __name__ == '__main__':
    unittest.main()
