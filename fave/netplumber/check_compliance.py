#!/usr/bin/env python2

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
import json

from netplumber.jsonrpc import check_compliance
from netplumber.jsonrpc import NET_PLUMBER_DEFAULT_PORT, NET_PLUMBER_DEFAULT_IP
from netplumber.jsonrpc import NET_PLUMBER_DEFAULT_UNIX

from util.print_util import eprint

def print_help():
    """ Prints usage to stderr.
    """

    eprint(
        "print_np -hsuf",
        "\t-h print this help and exit",
        "\t-f use this JSON file for compliance checking",
        "\t-s connect to net_plumber via tcp (ip=127.0.0.1, port=1234)",
        "\t-u connect to net_plumber via unix socket (/tmp/net_plumber.socket)",
        sep="\n"
    )



def main(argv):
    """ Connects to NetPlumber to let it print its state.
    """

    try:
        only_opts = lambda opts, _args: opts
        opts = only_opts(*getopt.getopt(argv, "hf:su"))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    use_tcp = True
    use_unix = False
    json_file = ""

    for opt, arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)

        elif opt == '-s':
            use_tcp = True
            use_unix = False

        elif opt == '-u':
            use_tcp = False
            use_unix = True

        elif opt == '-f':
            json_file = arg

        else:
            print_help()
            sys.exit(1)

    if not (use_tcp or use_unix):
        print_help()
        sys.exit(3)

    sock = socket.socket(
        (socket.AF_UNIX if use_unix else socket.AF_INET),
        socket.SOCK_STREAM
    )

    sock.connect(
        NET_PLUMBER_DEFAULT_UNIX if use_unix else (
            NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_PORT
        )
    )

    with open(json_file, "r") as checks:
        check_compliance([sock], json.load(checks))

    sock.close()

    sys.exit(0)


if __name__ == '__main__':
    main(sys.argv[1:])
