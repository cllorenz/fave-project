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

""" In-process tests for the three small NetPlumber/FaVe CLIs:
netplumber/print_np.py, netplumber/check_compliance.py, netplumber/dump_np.py.

Each is driven through `main(argv)` with its socket replaced by a recording
fake, so what is pinned is the CLI contract: which endpoint it connects to,
which RPC / message it sends for which flags, its exit codes, and (dump_np)
what it does to the output directory. Every guard `if __name__ == '__main__'`
is exercised once through runpy with `-h`, which exits before any connect.

No net_plumber, no FaVe aggregator: pure Python. dump_np's output directory is
always a fresh temporary directory, never the default `np_dump` in the tree.
"""

import contextlib
import io
import json
import os
import runpy
import socket
import sys
import tempfile
import unittest
import warnings
from unittest import mock

from netplumber import check_compliance, dump_np, print_np
from netplumber.jsonrpc import (
    NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_PORT, NET_PLUMBER_DEFAULT_UNIX
)
from util.aggregator_utils import (
    FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
)


class RecordingSocket:
    """ Stands in for `socket.socket(family, type)`: records the family, the
    address connected to and every request, and acknowledges each request
    with a success response, as net_plumber does. """

    instances = []

    def __init__(self, family=None, stype=None):
        self.family = family
        self.stype = stype
        self.address = None
        self.sent = []
        self.closed = False
        self._inbuf = b''
        RecordingSocket.instances.append(self)

    def connect(self, address):
        self.address = address

    def sendall(self, data):
        req = json.loads(data.decode('utf8'))
        self.sent.append(req)
        self._inbuf += (json.dumps(
            {"id": req["id"], "jsonrpc": "2.0", "result": 0}) + '\n').encode()

    def recv(self, bufsize, flags=0):
        chunk = self._inbuf[:bufsize]
        if not flags & socket.MSG_PEEK:
            self._inbuf = self._inbuf[bufsize:]
        return chunk

    def close(self):
        self.closed = True


def _run_main(main, argv):
    """ Run a CLI's main with a recording socket; return (exit code, the one
    socket it opened or None, stderr text). """
    RecordingSocket.instances = []
    err = io.StringIO()
    code = None
    with mock.patch.object(socket, 'socket', RecordingSocket), \
         contextlib.redirect_stderr(err):
        try:
            main(argv)
        except SystemExit as exc:
            code = exc.code
    socks = RecordingSocket.instances
    assert len(socks) <= 1, socks
    return code, (socks[0] if socks else None), err.getvalue()


@contextlib.contextmanager
def _capture_exit():
    """ Capture a SystemExit's code in the yielded box ('no exit' if none). """
    class Box:
        code = 'no exit'
    box = Box()
    try:
        yield box
    except SystemExit as exc:
        box.code = exc.code


def _run_as_script(module, argv):
    """ Execute a module as `__main__` (its guard included); return the exit
    code and stderr. """
    err = io.StringIO()
    with mock.patch.object(sys, 'argv', [module] + argv), \
         contextlib.redirect_stderr(err), warnings.catch_warnings():
        # runpy warns that the module is already imported; harmless here
        warnings.simplefilter('ignore', RuntimeWarning)
        with _capture_exit() as box:
            runpy.run_module(module, run_name='__main__')
    return box.code, err.getvalue()


class TestPrintNp(unittest.TestCase):
    """ print_np: -t/-n map to print_topology/print_plumbing_network. """

    def test_topology_and_network_over_tcp_by_default(self):
        code, sock, _ = _run_main(print_np.main, ['-t', '-n'])
        self.assertEqual(code, 0)
        self.assertEqual(sock.family, socket.AF_INET)
        self.assertEqual(sock.address,
                         (NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_PORT))
        self.assertEqual([r["method"] for r in sock.sent],
                         ["print_topology", "print_plumbing_network"])
        self.assertTrue(all(r["params"] is None for r in sock.sent))
        self.assertTrue(sock.closed)

    def test_no_print_flag_connects_and_sends_nothing(self):
        code, sock, _ = _run_main(print_np.main, ['-s'])
        self.assertEqual(code, 0)
        self.assertEqual(sock.sent, [])
        self.assertTrue(sock.closed)

    def test_unix_socket_path(self):
        """ Pinned: -u connects to /tmp/net_plumber.socket, a hard-coded path
        that is NOT jsonrpc.NET_PLUMBER_DEFAULT_UNIX (/dev/shm/np1.socket),
        which check_compliance uses for the same flag. """
        code, sock, _ = _run_main(print_np.main, ['-u', '-n'])
        self.assertEqual(code, 0)
        self.assertEqual(sock.family, socket.AF_UNIX)
        self.assertEqual(sock.address, "/tmp/net_plumber.socket")
        self.assertEqual([r["method"] for r in sock.sent],
                         ["print_plumbing_network"])

    def test_last_transport_flag_wins(self):
        _, sock, _ = _run_main(print_np.main, ['-u', '-s'])
        self.assertEqual(sock.family, socket.AF_INET)

    def test_help_exits_zero_without_connecting(self):
        code, sock, err = _run_main(print_np.main, ['-h'])
        self.assertEqual((code, sock), (0, None))
        self.assertIn("print_np", err)

    def test_unknown_option_exits_two(self):
        code, sock, err = _run_main(print_np.main, ['-x'])
        self.assertEqual((code, sock), (2, None))
        self.assertIn("-h print this help", err)

    def test_script_guard(self):
        code, err = _run_as_script('netplumber.print_np', ['-h'])
        self.assertEqual(code, 0)
        self.assertIn("print_np -hsutn", err)


class TestCheckCompliance(unittest.TestCase):
    """ check_compliance: sends the JSON file's content as the rule set. """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.rules = {"7": [[3, True, None], [4, False, "1xxx"]]}
        self.path = os.path.join(tmp.name, "checks.json")
        with open(self.path, "w", encoding="utf8") as handle:
            json.dump(self.rules, handle)

    def test_rules_from_file_are_sent_over_tcp(self):
        code, sock, _ = _run_main(check_compliance.main, ['-f', self.path])
        self.assertEqual(code, 0)
        self.assertEqual(sock.family, socket.AF_INET)
        self.assertEqual(sock.address,
                         (NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_PORT))
        self.assertEqual(len(sock.sent), 1)
        self.assertEqual(sock.sent[0]["method"], "check_compliance")
        self.assertEqual(sock.sent[0]["params"], {"rules": self.rules})
        self.assertTrue(sock.closed)

    def test_unix_socket_uses_the_jsonrpc_default(self):
        code, sock, _ = _run_main(check_compliance.main, ['-u', '-f', self.path])
        self.assertEqual(code, 0)
        self.assertEqual(sock.family, socket.AF_UNIX)
        self.assertEqual(sock.address, NET_PLUMBER_DEFAULT_UNIX)

    def test_tcp_flag_after_unix_switches_back(self):
        _, sock, _ = _run_main(check_compliance.main,
                               ['-u', '-s', '-f', self.path])
        self.assertEqual(sock.family, socket.AF_INET)

    def test_missing_file_option_fails_after_connecting(self):
        """ Pinned: without -f the CLI connects first and then fails opening
        '' -- a traceback, not the usage message, and the socket is left
        unclosed. """
        RecordingSocket.instances = []
        with mock.patch.object(socket, 'socket', RecordingSocket):
            with self.assertRaises(FileNotFoundError):
                check_compliance.main([])
        self.assertFalse(RecordingSocket.instances[0].closed)

    def test_help_and_bad_option(self):
        code, sock, err = _run_main(check_compliance.main, ['-h'])
        self.assertEqual((code, sock), (0, None))
        self.assertIn("-f use this JSON file", err)
        code, sock, _ = _run_main(check_compliance.main, ['-f'])  # no argument
        self.assertEqual((code, sock), (2, None))

    def test_script_guard(self):
        code, err = _run_as_script('netplumber.check_compliance', ['-h'])
        self.assertEqual(code, 0)
        self.assertIn("compliance checking", err)


class TestDumpNp(unittest.TestCase):
    """ dump_np: prepares the output directory, takes its lock and sends one
    `dump` event to FaVe describing what to dump. """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.odir = os.path.join(tmp.name, "dump")
        os.mkdir(self.odir)
        self.stale = os.path.join(self.odir, "old.json")
        with open(self.stale, "w", encoding="utf8") as handle:
            handle.write("{}")

        self.conn = mock.Mock(name="fave")
        patches = [
            mock.patch.object(dump_np, 'connect_to_fave', return_value=self.conn),
            mock.patch.object(dump_np, 'fave_sendmsg'),
        ]
        self.connect, self.sendmsg = [p.start() for p in patches]
        for patch in patches:
            self.addCleanup(patch.stop)

    def _sent(self):
        self.sendmsg.assert_called_once()
        conn, msg = self.sendmsg.call_args.args
        self.assertIs(conn, self.conn)
        return json.loads(msg)

    def test_every_flag_reaches_the_event_over_tcp(self):
        dump_np.main(['-a', '-f', '-n', '-p', '-t', '-o', self.odir])
        self.connect.assert_called_once_with(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
        self.assertEqual(self._sent(), {
            'type': 'dump', 'dir': self.odir, 'fave': True, 'flows': True,
            'network': True, 'pipes': True, 'trees': True, 'simple': False,
        })
        self.conn.close.assert_called_once_with()

    def test_a_dump_clears_the_directory_and_takes_its_lock(self):
        """ Old dump files are removed, and the lock FaVe releases when its
        dump is complete is held (persistently) by the CLI. """
        dump_np.main(['-f', '-o', self.odir])
        self.assertFalse(os.path.exists(self.stale))
        self.assertEqual(os.listdir(self.odir), ['.lock'])

    def test_simple_trees_imply_trees_and_unix_socket(self):
        dump_np.main(['-s', '-u', '-o', self.odir])
        self.connect.assert_called_once_with(FAVE_DEFAULT_UNIX)
        sent = self._sent()
        self.assertEqual((sent['trees'], sent['simple']), (True, True))
        self.assertEqual((sent['fave'], sent['flows'], sent['network'],
                          sent['pipes']), (False,) * 4)

    def test_a_missing_output_directory_is_created(self):
        odir = os.path.join(self.odir, "new", "deeper")
        dump_np.main(['-p', '-o', odir])
        self.assertTrue(os.path.isfile(os.path.join(odir, '.lock')))
        self.assertTrue(self._sent()['pipes'])

    def test_no_dump_flag_leaves_the_directory_alone(self):
        """ Nothing selected: the event is still sent (all False), but no
        existing file is removed. """
        dump_np.main(['-o', self.odir])
        self.assertTrue(os.path.exists(self.stale))
        sent = self._sent()
        self.assertFalse(any(sent[k] for k in
                             ('fave', 'flows', 'network', 'pipes', 'trees')))

    def test_help_and_bad_option_exit_before_connecting(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                dump_np.main(['-h'])
            self.assertEqual(ctx.exception.code, 0)
            with self.assertRaises(SystemExit) as ctx:
                dump_np.main(['-q'])
            self.assertEqual(ctx.exception.code, 2)
        self.assertIn("-o <dir> output directory", err.getvalue())
        self.connect.assert_not_called()

    def test_script_guard(self):
        code, err = _run_as_script('netplumber.dump_np', ['-h'])
        self.assertEqual(code, 0)
        self.assertIn("usage:", err)


if __name__ == '__main__':
    unittest.main()
