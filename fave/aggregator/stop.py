#!/usr/bin/env python2

import socket
import json

from aggregator import UDS_ADDR

aggr = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
aggr.connect(UDS_ADDR)

stop = {
    'type':'stop'
}

aggr.sendall(json.dumps(stop))
aggr.close()
