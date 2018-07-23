#!/usr/bin/env python2

import socket
from netplumber.jsonrpc import stop

server = ('localhost',1234)
s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect(server)

stop(s)

s.close()
