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

""" Tests for the pure helpers in the aggregator service. """

import unittest

from aggregator.aggregator_service import _parse_servers


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


if __name__ == '__main__':
    unittest.main()
