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

""" Wire-level tests for the NetPlumber JSON-RPC client (netplumber.jsonrpc)
that complement test_jsonrpc_client.py.

That file drives the encoders through a fake socket. This one covers what it
leaves out: framing over a REAL kernel socket (a `socketpair`, so `MSG_PEEK`
behaves as it does against net_plumber), connection set-up against a real
listening UNIX socket, the sharded bulk calls (`add_sources_bulk`), the
"dynamic distribution" switches that send nothing, the slice-matrix family,
and the affected-check tracking calls of INCREMENTAL_PLAN.md §6.3.

Pure Python: no net_plumber binary, no libnetplumber.
"""

import json
import os
import socket
import tempfile
import unittest
from unittest import mock

from netplumber import jsonrpc
from netplumber.jsonrpc import RPCError


class FakeSocket:
    """ Records sent requests and serves canned '\\n'-terminated responses,
    honouring the peek-then-consume pattern of `jsonrpc._sync_recv`. """

    def __init__(self):
        self.sent = []
        self._inbuf = b''

    def queue(self, obj):
        """ Queue one response object. """
        self._inbuf += (json.dumps(obj) + '\n').encode('utf8')

    def sendall(self, data):
        self.sent.append(json.loads(data.decode('utf8')))

    def recv(self, bufsize, flags=0):
        chunk = self._inbuf[:bufsize]
        if not flags & socket.MSG_PEEK:
            self._inbuf = self._inbuf[bufsize:]
        return chunk


def _ok(result=0, idx=0):
    return {"id": idx, "jsonrpc": "2.0", "result": result}


class _PairBase(unittest.TestCase):
    """ A connected UNIX socketpair: `client` is what jsonrpc talks to,
    `server` plays net_plumber. """

    def setUp(self):
        self.client, self.server = socket.socketpair()
        self.client.settimeout(5)
        self.server.settimeout(5)
        self.addCleanup(self.client.close)
        self.addCleanup(self.server.close)

    def server_reads_request(self):
        """ The one newline-terminated request the client sent. """
        buf = b''
        while not buf.endswith(b'\n'):
            buf += self.server.recv(65536)
        return json.loads(buf.decode('utf8'))


class TestFramingOverARealSocket(_PairBase):
    """ `_sync_recv` must return exactly ONE response per call, however the
    bytes arrive, and leave anything after the newline for the next call. """

    def test_two_back_to_back_responses_are_read_one_at_a_time(self):
        """ Both responses sit in the kernel buffer at once; the first read
        must consume only up to its own newline. """
        self.server.sendall(
            (json.dumps(_ok(11)) + '\n' + json.dumps(_ok(22)) + '\n').encode())
        first = jsonrpc._sync_recv([self.client])
        second = jsonrpc._sync_recv([self.client])
        self.assertEqual([first[0]["result"], second[0]["result"]], [11, 22])

    def test_a_response_longer_than_one_read_is_reassembled(self):
        """ A response bigger than the 4096-byte peek window has no newline in
        the first window, so it is consumed in parts and joined. """
        big = ["x" * 50] * 300            # ~16 KB of JSON
        self.server.sendall((json.dumps(_ok(big)) + '\n').encode())
        res = jsonrpc._sync_recv([self.client])
        self.assertEqual(res[0]["result"], big)

    def test_request_is_newline_terminated_json_rpc_2(self):
        """ `_async_send` frames each request with a trailing newline, the
        delimiter net_plumber's reader splits on. """
        self.server.sendall((json.dumps(_ok()) + '\n').encode())
        jsonrpc.print_table([self.client], 4)
        req = self.server_reads_request()
        self.assertEqual(req, {
            "id": 0, "jsonrpc": "2.0",
            "method": "print_table", "params": {"id": 4},
        })

    def test_sendrecv_returns_the_raw_response_text(self):
        """ `_sendrecv` (the synchronous helper) sends the message verbatim,
        WITHOUT a newline, and returns the decoded reply. """
        reply = json.dumps(_ok(5))
        self.server.sendall(reply.encode())
        out = jsonrpc._sendrecv(self.client, '{"ping": 1}')
        self.assertEqual(out, reply)
        self.assertEqual(self.server.recv(100), b'{"ping": 1}')

    def test_sendrecv_keeps_reading_while_reads_are_full(self):
        """ A reply that fills whole 4096-byte reads is read until a short
        read; nothing is lost at the boundary. """
        reply = "a" * 4096 + "b" * 10
        self.server.sendall(reply.encode())
        self.assertEqual(jsonrpc._sendrecv(self.client, "m"), reply)

    def test_multibyte_character_across_the_peek_window(self):
        """ `_sync_recv` once decoded each 4096-byte PEEK window as UTF-8 on its
        own, so a multi-byte character straddling the boundary made a valid
        response raise UnicodeDecodeError (TODO item 53). """
        prefix = '{"id": 0, "jsonrpc": "2.0", "result": "'
        pad = "a" * (4095 - len(prefix))      # 'ä' starts at byte 4095
        payload = (prefix + pad + 'ä"}\n').encode('utf8')
        self.assertEqual(payload[4095:4097], 'ä'.encode('utf8'))
        self.server.sendall(payload)
        [reply] = jsonrpc._sync_recv([self.client])
        self.assertEqual(reply['result'], pad + 'ä')

    def test_a_multibyte_character_does_not_leave_bytes_for_the_next_reply(self):
        """ The newline's index in the DECODED peek was used as a BYTE count to
        consume, so each multi-byte character before it left one byte of the
        response on the socket, and the NEXT response began with it (TODO
        item 53). """
        first = '{"id": 0, "jsonrpc": "2.0", "result": "äöü"}\n'
        second = '{"id": 1, "jsonrpc": "2.0", "result": 2}\n'
        self.server.sendall((first + second).encode('utf8'))
        self.assertEqual(jsonrpc._sync_recv([self.client])[0]['result'], 'äöü')
        self.assertEqual(jsonrpc._sync_recv([self.client])[0]['result'], 2)

class TestConsumeRaceGuard(unittest.TestCase):
    """ The consuming recv after a non-empty peek returning nothing means the
    peer closed in between; that must raise, not loop. """

    def test_empty_consume_after_a_nonempty_peek_raises(self):
        class Racy:
            def recv(self, _n, flags=0):
                return b'{"partial' if flags & socket.MSG_PEEK else b''

        with self.assertRaises(RPCError) as ctx:
            jsonrpc._sync_recv([Racy()])
        self.assertIn("while consuming", str(ctx.exception))


class TestConnectToNetPlumber(unittest.TestCase):
    """ connect_to_netplumber's success paths and its 'no socket' guard. """

    def test_connects_to_a_listening_unix_socket(self):
        """ port 0 selects a UNIX domain socket at the given path. """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "np.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(listener.close)
            listener.bind(path)
            listener.listen(1)

            sock = jsonrpc.connect_to_netplumber(path)
            self.addCleanup(sock.close)
            self.assertEqual(sock.family, socket.AF_UNIX)
            self.assertEqual(sock.getpeername(), path)

    def test_connects_over_tcp_when_a_port_is_given(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        sock = jsonrpc.connect_to_netplumber("127.0.0.1", port)
        self.addCleanup(sock.close)
        self.assertEqual(sock.family, socket.AF_INET)
        self.assertEqual(sock.getpeername(), ("127.0.0.1", port))

    def test_a_socket_that_cannot_be_created_is_reported(self):
        with mock.patch.object(jsonrpc.socket, "socket", return_value=None):
            with self.assertRaises(RPCError) as ctx:
                jsonrpc.connect_to_netplumber("/nowhere")
        self.assertIn("unix", str(ctx.exception))


class TestRemainingEncoders(unittest.TestCase):
    """ Method and params of the encoders test_jsonrpc_client.py leaves out. """

    def setUp(self):
        self.sock = FakeSocket()

    def _call(self, fn, *args):
        self.sock.queue(_ok())
        fn([self.sock], *args)
        return self.sock.sent[-1]

    def test_slice_matrix_family(self):
        cases = [
            (jsonrpc.add_slice_matrix, ("1,2\n2,1",),
             "add_slice_matrix", {"matrix": "1,2\n2,1"}),
            (jsonrpc.add_slice_allow, (1, 2),
             "add_slice_allow", {"id1": 1, "id2": 2}),
            (jsonrpc.remove_slice_allow, (3, 4),
             "remove_slice_allow", {"id1": 3, "id2": 4}),
            (jsonrpc.dump_slices_pipes, ("/out",),
             "dump_slices_pipes", {"dir": "/out"}),
        ]
        for fn, args, method, params in cases:
            with self.subTest(method=method):
                req = self._call(fn, *args)
                self.assertEqual((req["method"], req["params"]), (method, params))

    def test_parameterless_calls_send_no_params_key(self):
        """ These build only the basic envelope plus a method. """
        for fn, method in [
                (jsonrpc.remove_slice_matrix, "remove_slice_matrix"),
                (jsonrpc.print_slice_matrix, "print_slice_matrix")]:
            with self.subTest(method=method):
                req = self._call(fn)
                self.assertEqual(req, {"id": 0, "jsonrpc": "2.0", "method": method})

    def test_set_track_affected_coerces_to_bool(self):
        self.assertEqual(
            self._call(jsonrpc.set_track_affected, 1)["params"], {"on": True})
        self.assertEqual(
            self._call(jsonrpc.set_track_affected, [])["params"], {"on": False})
        self.assertEqual(self.sock.sent[-1]["method"], "set_track_affected")


class TestTakeAffected(unittest.TestCase):
    """ take_affected unites (source, probe) pairs over every instance. """

    def test_pairs_are_united_over_sockets_as_int_tuples(self):
        s0, s1 = FakeSocket(), FakeSocket()
        s0.queue(_ok([[1, 2], ["3", "4"]]))
        s1.queue(_ok([[1, 2], [5, 6]]))
        pairs = jsonrpc.take_affected([s0, s1])
        self.assertEqual(pairs, {(1, 2), (3, 4), (5, 6)})
        for sock in (s0, s1):
            self.assertEqual(sock.sent[-1]["method"], "take_affected")
            self.assertEqual(sock.sent[-1]["params"], {})

    def test_a_null_result_is_no_pairs(self):
        sock = FakeSocket()
        sock.queue(_ok(None))
        self.assertEqual(jsonrpc.take_affected([sock]), set())

    def test_an_error_response_raises(self):
        sock = FakeSocket()
        sock.queue({"id": 0, "jsonrpc": "2.0",
                    "error": {"code": -1, "message": "no tracking"}})
        with self.assertRaises(RPCError) as ctx:
            jsonrpc.take_affected([sock])
        self.assertIn("no tracking", str(ctx.exception))

    def test_an_error_member_with_code_zero_still_raises(self):
        """ Pinned: unlike every other call (where code 0 means success,
        `_parse_msg`), take_affected raises on ANY "error" member, falling back
        to a generic message when it carries none. """
        sock = FakeSocket()
        sock.queue({"id": 0, "jsonrpc": "2.0", "error": {"code": 0},
                    "result": [[1, 2]]})
        with self.assertRaises(RPCError) as ctx:
            jsonrpc.take_affected([sock])
        self.assertIn("take_affected failed", str(ctx.exception))


class TestBulkSources(unittest.TestCase):
    """ add_sources_bulk shards sources over instances by index and maps each
    response's id to the node id it returns. """

    def test_sources_are_sharded_and_ids_mapped(self):
        s0, s1 = FakeSocket(), FakeSocket()
        # responses carry the request id (= source index) and the node id
        s0.queue(_ok(100, idx=0))
        s0.queue(_ok(102, idx=2))
        s1.queue(_ok(101, idx=1))
        sources = [
            (0, ["1xxx"], [], [10]),
            (1, ["1xxx", "0xxx"], [], [11]),
            (2, ["1xxx"], ["11xx"], [12]),
        ]
        sids = jsonrpc.add_sources_bulk([s0, s1], sources)

        self.assertEqual(sids, {0: 100, 1: 101, 2: 102})
        self.assertEqual([r["id"] for r in s0.sent], [0, 2])
        self.assertEqual([r["id"] for r in s1.sent], [1])
        # one vector, no diff -> compact form; otherwise the list/diff form
        self.assertEqual(s0.sent[0]["params"], {"id": 0, "hs": "1xxx", "ports": [10]})
        self.assertEqual(s1.sent[0]["params"]["hs"],
                         {"list": ["1xxx", "0xxx"], "diff": []})
        self.assertEqual(s0.sent[1]["params"]["hs"],
                         {"list": ["1xxx"], "diff": ["11xx"]})
        self.assertTrue(all(r["method"] == "add_source" for r in s0.sent + s1.sent))

    def test_dynamic_distribution_sends_nothing_and_echoes_indices(self):
        sock = FakeSocket()
        sids = jsonrpc.add_sources_bulk(
            [sock], [(4, ["1"], [], [1]), (7, ["0"], ["1"], [2])], use_dynamic=True)
        self.assertEqual(sids, {4: 4, 7: 7})
        self.assertEqual(sock.sent, [])


class TestDynamicSwitches(unittest.TestCase):
    """ The use_dynamic paths are stubs (dynamic_distribution is disabled):
    they must send nothing rather than half a protocol exchange. """

    def test_add_source_dynamic_returns_index_unsent(self):
        sock = FakeSocket()
        self.assertEqual(
            jsonrpc.add_source([sock], 3, ["1x"], [], [9], use_dynamic=True), 3)
        self.assertEqual(sock.sent, [])

    def test_add_source_shards_by_index(self):
        """ Without dynamic distribution the source goes to socks[idx % n]. """
        s0, s1 = FakeSocket(), FakeSocket()
        s1.queue(_ok(77))
        self.assertEqual(jsonrpc.add_source([s0, s1], 3, ["1x"], [], [9]), 77)
        self.assertEqual((s0.sent, s1.sent[0]["params"]["id"]), ([], 3))

    def test_add_links_bulk_dynamic_sends_nothing(self):
        sock = FakeSocket()
        jsonrpc.add_links_bulk([sock], [(0, 1, 2), (-1, 3, 4)], use_dynamic=True)
        self.assertEqual(sock.sent, [])

    def test_add_links_bulk_carries_the_link_index_as_request_id(self):
        sock = FakeSocket()
        sock.queue(_ok(idx=5))
        jsonrpc.add_links_bulk([sock], [(5, 0x10001, 0x20001)])
        self.assertEqual(sock.sent, [{
            "id": 5, "jsonrpc": "2.0", "method": "add_link",
            "params": {"from_port": 0x10001, "to_port": 0x20001},
        }])


if __name__ == '__main__':
    unittest.main()
