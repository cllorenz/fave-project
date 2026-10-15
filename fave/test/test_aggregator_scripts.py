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

""" The aggregator's command-line edges: `aggregator/stop.py`,
`reporting/report.py`, `aggregator_service.main`, and the client side of the
wire (`connect_to_fave`, `fave_recvmsg`'s logging and short-read paths).

`stop.py` and `report.py` are module-level scripts that parse `sys.argv` at
import, so they are executed IN-PROCESS with `runpy` (coverage does not follow
subprocesses here). `connect_to_fave` is replaced by one end of a
`socketpair`, and the test reads what the script sent off the other end with
the real `fave_recvmsg` -- so the frame format is checked, not assumed. For
`report.py` the barrier handshake is real as well: a helper thread plays the
aggregator, reads the request and releases the barrier it names.

`main` is run with the engine, the reporter, the signal handlers and `run`
replaced; its log goes to a temporary `log_dir`. No TCP port is ever bound
except an ephemeral one on 127.0.0.1 for the TCP connect test.
"""

# pylint: disable=protected-access

import json
import logging
import os
import runpy
import socket
import sys
import tempfile
import threading
import unittest

from unittest import mock

import aggregator.aggregator_service as aggregator_service
import util.aggregator_utils as aggregator_utils
from aggregator.aggregator_abstract import TRACE
from aggregator.aggregator_service import AggregatorService
from netplumber import jsonrpc
from util import barrier
from util.aggregator_utils import (
    FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX,
    connect_to_fave, fave_recvmsg, fave_sendmsg
)

_FAVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STOP = os.path.join(_FAVE, 'aggregator', 'stop.py')
_REPORT = os.path.join(_FAVE, 'reporting', 'report.py')


class _ScriptBase(unittest.TestCase):
    """ Runs a script with a fake `connect_to_fave` that hands out one end of
    a socketpair and records where it was asked to connect. """

    def setUp(self):
        self.client, self.server = socket.socketpair()
        self.addCleanup(self.server.close)
        self.addCleanup(self.client.close)
        self.connected_to = []

        def fake_connect(*args):
            self.connected_to.append(args)
            return self.client

        patcher = mock.patch.object(aggregator_utils, 'connect_to_fave', fake_connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, script, *argv):
        with mock.patch.object(sys, 'argv', [script] + list(argv)):
            runpy.run_path(script, run_name='__main__')

    def _received(self):
        return json.loads(fave_recvmsg(self.server))


class TestStopScript(_ScriptBase):
    """ stop.py sends exactly one `{"type": "stop"}` frame and closes. """

    def test_default_target_is_the_tcp_default(self):
        self._run(_STOP)
        self.assertEqual(self.connected_to, [(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)])
        self.assertEqual(self._received(), {'type': 'stop'})
        # the script closed its end: nothing further arrives
        self.assertIsNone(fave_recvmsg(self.server))

    def test_server_and_port_are_honoured(self):
        self._run(_STOP, '-s', '10.0.0.1', '-p', '45000')
        self.assertEqual(self.connected_to, [('10.0.0.1', 45000)])
        self.assertEqual(self._received(), {'type': 'stop'})

    def test_unix_flag_uses_the_default_socket(self):
        self._run(_STOP, '-u')
        self.assertEqual(self.connected_to, [(FAVE_DEFAULT_UNIX,)])
        self.assertEqual(self._received(), {'type': 'stop'})


class TestReportScript(_ScriptBase):
    """ report.py asks for `report.md` under a barrier and BLOCKS until the
    aggregator releases it (TODO.md item 1r): returning early would let the
    caller convert the previous run's report. """

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(barrier, 'BARRIER_DIR', self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        # this test process plays the live aggregator the waiter checks on
        barrier.publish_owner(self.tmp.name)

    def _aggregator(self, error=None):
        """ Read one request, record it, release its barrier. """
        box = {}

        def serve():
            request = self._received()
            box['request'] = request
            # the waiter must still be blocked: the barrier is armed
            with open(request['barrier'], encoding='utf-8') as bfile:
                box['state_before'] = json.load(bfile)['state']
            barrier.release(request['barrier'], error=error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return thread, box

    def test_it_returns_after_the_aggregator_releases(self):
        thread, box = self._aggregator()
        self._run(_REPORT, '-u')
        thread.join(5)

        self.assertEqual(self.connected_to, [(FAVE_DEFAULT_UNIX,)])
        request = box['request']
        self.assertEqual(request['type'], 'report')
        self.assertEqual(request['file'], 'report.md')
        self.assertEqual(os.path.dirname(request['barrier']), self.tmp.name)
        self.assertEqual(box['state_before'], 'armed')
        # the waiter consumed the barrier file
        self.assertFalse(os.path.exists(request['barrier']))

    def test_a_failed_report_is_raised_not_swallowed(self):
        thread, _box = self._aggregator(error='OSError: disk full')
        with self.assertRaises(barrier.BarrierError) as ctx:
            self._run(_REPORT, '-s', '10.0.0.2', '-p', '45001')
        thread.join(5)
        self.assertEqual(self.connected_to, [('10.0.0.2', 45001)])
        self.assertIn('disk full', str(ctx.exception))


class TestConnectToFave(unittest.TestCase):
    """ connect_to_fave: AF_UNIX for port 0, AF_INET otherwise, retrying a
    refused connect before giving up with the address in the message. """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_unix_roundtrip(self):
        path = os.path.join(self.tmp.name, 'fave.socket')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(path)
        listener.listen(1)

        conn = connect_to_fave(path)
        self.addCleanup(conn.close)
        self.assertEqual(conn.family, socket.AF_UNIX)
        peer, _ = listener.accept()
        self.addCleanup(peer.close)
        fave_sendmsg(conn, '{"type": "stop"}')
        self.assertEqual(fave_recvmsg(peer), '{"type": "stop"}')

    def test_tcp_on_an_ephemeral_port(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        conn = connect_to_fave('127.0.0.1', port)
        self.addCleanup(conn.close)
        self.assertEqual(conn.family, socket.AF_INET)
        self.assertEqual(conn.getpeername(), ('127.0.0.1', port))

    def test_no_listener_retries_ten_times_then_raises(self):
        path = os.path.join(self.tmp.name, 'absent.socket')
        with mock.patch.object(aggregator_utils.time, 'sleep') as sleep:
            with self.assertRaises(Exception) as ctx:
                connect_to_fave(path)
        self.assertEqual(sleep.call_count, 10)
        self.assertEqual(str(ctx.exception), 'could not connect to fave: %s' % path)

    def test_tcp_failure_names_host_and_port(self):
        # bind but never listen: a connect to it is refused
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(holder.close)
        holder.bind(('127.0.0.1', 0))
        port = holder.getsockname()[1]
        with mock.patch.object(aggregator_utils.time, 'sleep'):
            with self.assertRaises(Exception) as ctx:
                connect_to_fave('127.0.0.1', port)
        self.assertEqual(
            str(ctx.exception), 'could not connect to fave: 127.0.0.1 %d' % port)


class TestRecvmsgLogging(unittest.TestCase):
    """ fave_recvmsg reports, through the given logger, why it returned None. """

    def setUp(self):
        self.left, self.right = socket.socketpair()
        self.addCleanup(self.left.close)
        self.addCleanup(self.right.close)
        self.logger = logging.getLogger('test_aggregator_scripts.recv')

    def test_a_closed_peer_is_logged(self):
        self.left.close()
        with self.assertLogs(self.logger, level='WARNING') as logs:
            self.assertIsNone(fave_recvmsg(self.right, logger=self.logger))
        self.assertIn('failed to read message length', logs.output[0])

    def test_a_truncated_frame_is_logged_with_its_progress(self):
        # announce 10 bytes, deliver 3, hang up
        self.left.sendall(b'\x00\x00\x00\x0aabc')
        self.left.close()
        with self.assertLogs(self.logger, level='DEBUG') as logs:
            self.assertIsNone(fave_recvmsg(self.right, logger=self.logger))
        text = '\n'.join(logs.output)
        self.assertIn('message length is 10', text)
        self.assertIn('data so far: 3', text)


class _FakeEngine:
    """ Records nothing; just answers the configuration stamp main() logs. """

    def configuration_stamp(self):
        return {'impl': 'first-party', 'solver': 'stub'}

    def max_rule_index(self, table):
        return 2**20 - 1


class TestMain(unittest.TestCase):
    """ aggregator_service.main: flags reach the service, the backend stamp is
    logged in the shape `cell_run.py` parses, and command-line errors exit 1
    instead of raising. """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        logger = AggregatorService.LOGGER
        handlers, level = list(logger.handlers), logger.level
        saved = (logging._srcfile, logging.logThreads, logging.logProcesses)

        def restore():
            for handler in logger.handlers[:]:
                if handler not in handlers:
                    logger.removeHandler(handler)
                    handler.close()
            logger.setLevel(level)
            logging._srcfile, logging.logThreads, logging.logProcesses = saved
        self.addCleanup(restore)

        self.build = mock.MagicMock(name='build_engine', return_value=_FakeEngine())
        self.run = mock.MagicMock(name='run')
        for target, value in (
                ('build_engine', self.build),
                ('Reporter', mock.MagicMock(name='Reporter')),
                ('register_signals', mock.MagicMock(name='register_signals'))):
            patcher = mock.patch.object(aggregator_service, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(AggregatorService, 'run', self.run)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {'log_dir': self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        # main() rebinds the module's AGGREGATOR global; put it back after
        patcher = mock.patch.object(aggregator_service, 'AGGREGATOR', None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _log(self):
        with open(os.path.join(self.tmp.name, 'aggregator.log'),
                  encoding='utf-8') as lfile:
            return lfile.read()

    def test_ad6_backend_needs_no_netplumber_and_logs_its_stamp(self):
        with mock.patch.object(jsonrpc, 'connect_to_netplumber') as connect:
            aggregator_service.main([
                '-b', 'ad6', '--solver', 'cadical', '--grounding', 'full',
                '--lite-acyclic', '-u'])
        connect.assert_not_called()
        _, kwargs = self.build.call_args
        self.assertEqual(self.build.call_args[0][0], 'ad6')
        self.assertEqual(kwargs['socks'], [])
        self.assertEqual(
            (kwargs['solver'], kwargs['grounding'], kwargs['lite_acyclic']),
            ('cadical', 'full', True))
        self.run.assert_called_once_with(FAVE_DEFAULT_UNIX)
        self.assertIn(
            "backend: ad6 {'impl': 'first-party', 'solver': 'stub', "
            "'stable_indices': True}", self._log())
        self.assertEqual(AggregatorService.LOGGER.level, logging.INFO)
        self.assertIsNotNone(aggregator_service.AGGREGATOR)

    def test_netplumber_connects_every_server_and_listens_on_tcp(self):
        socks = {('10.0.0.1', 1): 'S1', ('10.0.0.2', 2): 'S2'}
        with mock.patch.object(
                jsonrpc, 'connect_to_netplumber',
                side_effect=lambda h, p: socks[(h, p)]) as connect:
            aggregator_service.main([
                '-S', '10.0.0.1:1,10.0.0.2:2', '-s', '127.0.0.5', '-p', '45555',
                '-a', '-d'])
        self.assertEqual(connect.call_count, 2)
        _, kwargs = self.build.call_args
        self.assertEqual(sorted(kwargs['socks']), ['S1', 'S2'])
        # -a registers a (placeholder) dynamic socket per server
        self.assertEqual(kwargs['asyncore_socks'],
                         {('10.0.0.1', 1): None, ('10.0.0.2', 2): None})
        self.run.assert_called_once_with('127.0.0.5', port=45555)
        self.assertEqual(AggregatorService.LOGGER.level, logging.DEBUG)

    def test_trace_flag_selects_the_trace_level(self):
        with mock.patch.object(jsonrpc, 'connect_to_netplumber'):
            aggregator_service.main(['-t'])
        self.assertEqual(AggregatorService.LOGGER.level, TRACE)

    def test_an_unreachable_netplumber_exits_1(self):
        with mock.patch.object(
                jsonrpc, 'connect_to_netplumber',
                side_effect=jsonrpc.RPCError('refused')), \
                mock.patch('sys.stderr') as stderr, \
                mock.patch('sys.stdout'):
            with self.assertRaises(SystemExit) as ctx:
                aggregator_service.main(['-S', '10.0.0.9:9'])
        self.assertEqual(ctx.exception.code, 1)
        written = ''.join(c[0][0] for c in stderr.write.call_args_list)
        self.assertIn('could not connect to server: 10.0.0.9 9', written)
        self.run.assert_not_called()
        self.assertIn('refused', self._log())

    def test_a_bad_backend_option_exits_1_with_its_reason(self):
        self.build.side_effect = ValueError('unknown solver')
        with mock.patch('sys.stderr') as stderr:
            with self.assertRaises(SystemExit) as ctx:
                aggregator_service.main(['-b', 'ad6', '--solver', 'nope'])
        self.assertEqual(ctx.exception.code, 1)
        written = ''.join(c[0][0] for c in stderr.write.call_args_list)
        self.assertIn('backend configuration error: unknown solver', written)
        self.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
