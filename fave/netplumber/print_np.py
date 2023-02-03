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

""" This module provides functionality to let NetPlumber print its state.
"""

import sys
import getopt
import socket

import netplumber.jsonrpc as jsonrpc


def print_help():
    """ Prints usage to stderr.
    """

    print(
        "print_np -hsutn",
        "\t-h print this help and exit",
        "\t-n print net_plumber network",
        "\t-t print the topology",
        "\t-s connect to net_plumber via tcp (ip=127.0.0.1, port=1234)",
        "\t-u connect to net_plumber via unix socket (/tmp/net_plumber.socket)",
        sep="\n",
        file=sys.stderr
    )



def main(argv):
    """ Connects to NetPlumber to let it print its state.
    """

    try:
        only_opts = lambda opts, _args: opts
        opts = only_opts(*getopt.getopt(argv, "htnsu"))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    use_tcp = True
    use_unix = False
    print_topo = False
    print_nw = False

    for opt in [oa[0] for oa in opts]:
        if opt == '-h':
            print_help()
            sys.exit(0)

        elif opt == '-s':
            use_tcp = True
            use_unix = False

        elif opt == '-u':
            use_tcp = False
            use_unix = True

        elif opt == '-t':
            print_topo = True

        elif opt == '-n':
            print_nw = True

        else:
            print_help()
            sys.exit(1)

    if use_tcp:
        server = "127.0.0.1"
        port = 1234

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server, port))

    elif use_unix:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect("/tmp/net_plumber.socket")

    else:
        print_help()
        sys.exit(3)

    if print_topo:
        jsonrpc.print_topology(sock)

    if print_nw:
        jsonrpc.print_plumbing_network(sock)

    sock.close()

    sys.exit(0)


if __name__ == '__main__':
    main(sys.argv[1:])
