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

UDS_ADDR = "/tmp/np_aggregator.socket"

def connect_to_fave():
    """ Creates a connected socket to FaVe.
    """

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    if not sock:
        raise Exception(
            "could not create unix socket"
        )

    tries = 5
    while tries > 0:
        try:
            sock.connect(UDS_ADDR)
            break
        except socket.error:
            time.sleep(1)
            tries -= 1

    try:
        sock.getpeername()
    except socket.error:
        raise Exception("could not connect to fave: %s" % UDS_ADDR)

    return sock
