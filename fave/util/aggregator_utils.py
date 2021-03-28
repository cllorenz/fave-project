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

""" This module provides aggregator functionality utilized across Fave.
"""

import time
import socket

FAVE_DEFAULT_UNIX = "/dev/shm/np_aggregator.socket"
FAVE_DEFAULT_IP = '127.0.0.1'
FAVE_DEFAULT_PORT = 44000

def connect_to_fave(server, port=0):
    """ Creates a connected socket to FaVe.
    """

    if port == 0:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if not sock:
        raise Exception(
            "could not create socket for %s" % ('unix' if port == 0 else 'tcp/ip')
        )

    tries = 5
    while tries > 0:
        try:
            if port == 0:
                sock.connect(server)
            else:
                sock.connect((server, port))
            break
        except socket.error:
            time.sleep(1)
            tries -= 1

    try:
        sock.getpeername()
    except socket.error:
        if port == 0:
            raise Exception("could not connect to fave: %s" % server)
        else:
            raise Exception("could not connect to fave: %s %s" % (server, port))

    return sock
