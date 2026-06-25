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

""" Tests the length-prefixed wire framing used for every FaVe <-> aggregator
message. Driven over a real socketpair() -- no mocks, no live backend.
"""

import socket
import unittest

from util.aggregator_utils import fave_sendmsg, fave_recvmsg


class TestFaveFraming(unittest.TestCase):
    """ Tests fave_sendmsg / fave_recvmsg / _recvall. """

    def setUp(self):
        self.a, self.b = socket.socketpair()

    def tearDown(self):
        self.a.close()
        self.b.close()

    def test_roundtrip_simple(self):
        fave_sendmsg(self.a, 'hello fave')
        self.assertEqual(fave_recvmsg(self.b), 'hello fave')

    def test_roundtrip_unicode_and_large(self):
        """ A multibyte / multi-recv payload reassembles exactly. """
        payload = ('ä' * 5000) + '✓'
        fave_sendmsg(self.a, payload)
        self.assertEqual(fave_recvmsg(self.b), payload)

    def test_two_messages_are_independently_framed(self):
        """ Back-to-back messages are delimited by their length prefix. """
        fave_sendmsg(self.a, 'first')
        fave_sendmsg(self.a, 'second')
        self.assertEqual(fave_recvmsg(self.b), 'first')
        self.assertEqual(fave_recvmsg(self.b), 'second')

    def test_recv_on_closed_peer_returns_none(self):
        """ Reading after the peer closed yields None (empty length read). """
        self.a.close()
        self.assertIsNone(fave_recvmsg(self.b))

    def test_empty_message_roundtrip(self):
        """ A zero-length payload frames and decodes to the empty string. """
        fave_sendmsg(self.a, '')
        self.assertEqual(fave_recvmsg(self.b), '')


if __name__ == '__main__':
    unittest.main()
