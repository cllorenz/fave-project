#!/usr/bin/env python2

import sys
import socket
import netplumber.jsonrpc as jsonrpc

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(1)

    server = "127.0.0.1"
    port = 1234

    np = (server,port)
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.connect(np)

    if sys.argv[1] == '-t':
        jsonrpc.print_topology(sock)

    elif sys.argv[1] == '-n':
        jsonrpc.print_plumbing_network(sock)

    sock.close()

    sys.exit(0)
