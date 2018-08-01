#!/usr/bin/env python2

""" This script sends a stopping event to FaVe.
"""

import socket
import json

from aggregator import UDS_ADDR

_AGGR = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
_AGGR.connect(UDS_ADDR)

_STOP = {
    'type':'stop'
}

_AGGR.sendall(json.dumps(_STOP))
_AGGR.close()
