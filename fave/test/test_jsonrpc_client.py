#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2024 Claas Lorenz <claas_lorenz@genua.de>

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

""" Contract tests for the NetPlumber JSON-RPC *client* (netplumber.jsonrpc).

    These validate that the client serialises the correct JSON-RPC requests and
    parses responses correctly -- the protocol/transport surface -- using a fake
    socket. They need NO running NetPlumber backend, so they live in the fast
    tier. (End-to-end behaviour against the real engine is covered by the e2e
    tier's test_rpc.py.)
"""

import json
import socket
import unittest
from unittest import mock

from netplumber import jsonrpc
from netplumber.jsonrpc import RPCError


class FakeSocket:
    """ Records sent payloads and serves canned newline-delimited JSON responses.

    Models the `recv(.., MSG_PEEK)`-then-consuming-`recv` pattern used by
    jsonrpc._sync_recv: a peek returns buffered bytes without consuming them; a
    plain recv consumes them.
    """

    def __init__(self):
        self.sent = []      # decoded request strings, in send order
        self.closed = False
        self._inbuf = b''   # pending response bytes

    def queue_response(self, obj):
        """ Queue one JSON object to be returned as a '\\n'-terminated response. """
        self._inbuf += (json.dumps(obj) + '\n').encode('utf8')

    def sendall(self, data):
        self.sent.append(data.decode('utf8').rstrip('\n'))

    def recv(self, bufsize, flags=0):
        if flags & socket.MSG_PEEK:
            return self._inbuf[:bufsize]            # peek: do not consume
        chunk = self._inbuf[:bufsize]
        self._inbuf = self._inbuf[bufsize:]         # consume
        return chunk

    def close(self):
        self.closed = True

    def last_request(self):
        return json.loads(self.sent[-1])


def _ok(result=0):
    return {"id": 0, "jsonrpc": "2.0", "result": result}


class TestJsonRpcClientRequests(unittest.TestCase):
    """ Each RPC function must emit the documented method + params. """

    def setUp(self):
        self.sock = FakeSocket()
        self.socks = [self.sock]

    def test_init(self):
        self.sock.queue_response(_ok())
        jsonrpc.init(self.socks, 8)
        req = self.sock.last_request()
        self.assertEqual(req["jsonrpc"], "2.0")
        self.assertEqual(req["method"], "init")
        self.assertEqual(req["params"], {"length": 8})

    def test_destroy(self):
        self.sock.queue_response(_ok())
        jsonrpc.destroy(self.socks)
        self.assertEqual(self.sock.last_request()["method"], "destroy")

    def test_add_table(self):
        self.sock.queue_response(_ok())
        jsonrpc.add_table(self.socks, 1, [1, 2, 3])
        req = self.sock.last_request()
        self.assertEqual(req["method"], "add_table")
        self.assertEqual(req["params"], {"id": 1, "in": [1, 2, 3]})

    def test_add_link(self):
        self.sock.queue_response(_ok())
        jsonrpc.add_link(self.socks, 10, 11)
        req = self.sock.last_request()
        self.assertEqual(req["method"], "add_link")
        self.assertEqual(req["params"], {"from_port": 10, "to_port": 11})

    def test_remove_rule(self):
        self.sock.queue_response(_ok())
        jsonrpc.remove_rule(self.socks, 4242)
        req = self.sock.last_request()
        self.assertEqual(req["method"], "remove_rule")
        self.assertEqual(req["params"], {"node": 4242})

    def test_add_rule_request_and_return(self):
        # add_rule returns the node id parsed from the response "result".
        self.sock.queue_response(_ok(result=987654321))
        node = jsonrpc.add_rule(self.socks, 1, 2, [1], [2], "xxxxxxx0", None, None)
        req = self.sock.last_request()
        self.assertEqual(req["method"], "add_rule")
        self.assertEqual(req["params"], {
            "table": 1, "index": 2, "in": [1], "out": [2],
            "match": "xxxxxxx0", "mask": None, "rw": None,
        })
        self.assertEqual(node, 987654321)   # response parsing


class TestJsonRpcClientResponses(unittest.TestCase):
    """ Response parsing and error handling. """

    def setUp(self):
        self.sock = FakeSocket()
        self.socks = [self.sock]

    def test_error_response_raises(self):
        self.sock.queue_response(
            {"id": 0, "jsonrpc": "2.0", "error": {"code": 1, "message": "boom"}}
        )
        with self.assertRaises(RPCError):
            jsonrpc.add_table(self.socks, 1, [1])

    def test_error_code_zero_is_not_an_error(self):
        # code 0 means success -> must not raise.
        self.sock.queue_response(
            {"id": 0, "jsonrpc": "2.0", "error": {"code": 0, "message": ""}, "result": 0}
        )
        jsonrpc.init(self.socks, 1)

    def test_broadcast_to_all_sockets(self):
        s1, s2 = FakeSocket(), FakeSocket()
        s1.queue_response(_ok())
        s2.queue_response(_ok())
        jsonrpc.init([s1, s2], 4)
        self.assertEqual(json.loads(s1.sent[-1])["method"], "init")
        self.assertEqual(json.loads(s2.sent[-1])["method"], "init")


class TestJsonRpcConnect(unittest.TestCase):
    """ connect_to_netplumber error path (regression guard). """

    def test_connect_failure_raises_clean_rpcerror(self):
        # Regression guard: the failure message formats the (host, port) endpoint.
        # A previous bug did `"%s" % (server, port)` -- a 2-tuple into one %s --
        # which raised TypeError instead of a clean RPCError.
        class DeadSocket:
            def setblocking(self, _flag):
                pass

            def connect(self, _addr):
                raise socket.error("refused")

            def getpeername(self):
                raise socket.error("not connected")

        with mock.patch.object(jsonrpc.socket, "socket", return_value=DeadSocket()), \
             mock.patch.object(jsonrpc.time, "sleep"):   # no real waiting
            with self.assertRaises(RPCError) as ctx:
                jsonrpc.connect_to_netplumber("127.0.0.1", 44001)

        self.assertIn("44001", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
