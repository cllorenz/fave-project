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
import struct
import logging

FAVE_DEFAULT_UNIX = "/dev/shm/np_aggregator.socket"
FAVE_DEFAULT_IP = '127.0.0.1'
FAVE_DEFAULT_PORT = 44000

def connect_to_fave(server, port=0):
    """ Creates a connected socket to FaVe.
    """

    sock = socket.socket(
        socket.AF_UNIX if port == 0 else socket.AF_INET,
        socket.SOCK_STREAM
    )

    if not sock:
        raise Exception(
            "could not create socket for %s" % ('unix' if port == 0 else 'tcp/ip')
        )

    tries = 10
    while tries > 0:
        try:
            sock.connect(server if port == 0 else (server, port))
            break
        except socket.error:
            time.sleep(0.1)
            tries -= 1

    try:
        sock.getpeername()
    except socket.error:
        server_str = server if port == 0 else "%s %s" % (server, port)
        raise Exception("could not connect to fave: %s" % server_str)

    return sock


def fave_sendmsg(conn, data):
    """ Send a message to FaVe.

    Arguments:
    conn -- a connected socket
    data -- the message as string
    """

    msg = struct.pack('>I', len(data)) + data
    return conn.sendall(msg)


def fave_recvmsg(conn, logger=None):
    """ Receive a message from FaVe.

    Arguments:
    conn -- a connected socket

    Keyword arguments:
    logger -- a logger instance (default: None)
    """

    raw_msglen = conn.recv(4)
    if not raw_msglen:
        logger.warn("fave_recvmsg: failed to read message length")
        return None
    msglen = struct.unpack('>I', raw_msglen)[0]
    if logger and logger.isEnabledFor(logging.DEBUG):
        logger.debug("fave_recvmsg: message length is %s" % msglen)
    return _recvall(conn, msglen, logger=logger)

def _recvall(conn, msglen, logger=None):
    data = bytearray()
    while len(data) < msglen:
        part = conn.recv(msglen - len(data))
        if not part:
            logger.warn("fave_recvmsg: received empty data. data so far: %s" % len(data))
            return None
        data.extend(part)
    return str(data)
