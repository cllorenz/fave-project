#!/usr/bin/env python2

""" Stops NetPlumber via JSONRPC.
"""

import socket
from netplumber.jsonrpc import stop

SERVER = ('localhost', 1234)

SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
SOCK.connect(SERVER)

stop(SOCK)

SOCK.close()
