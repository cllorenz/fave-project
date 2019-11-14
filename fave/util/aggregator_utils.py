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
