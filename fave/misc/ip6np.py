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

""" This module provides functionality to send ip6tables configurations to FaVe.
"""

import sys
import argparse
import json
import pprint

from iptables.generator import generate
from iptables.parser_singleton import PARSER

from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
from util.aggregator_utils import connect_to_fave, fave_sendmsg

def _try_int(var):
    try:
        int(var)
        return True
    except ValueError:
        return False


def _parse_ports(arg):
    ports = [1, 2]

    if isinstance(arg, list):
        ports = arg
    elif _try_int(arg):
        ports = [str(x) for x in range(1, int(arg)+1)]
    else:
        ports = arg.split(',')

    return ports



def main(argv):
    """ Connects to FaVe and sends an ip6tables configuration event.
    """

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-d', '--dump',
        dest='dump',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-n', '--node',
        dest='node'
    )
    parser.add_argument(
        '-i', '--ip',
        dest='address'
    )
    parser.add_argument(
        '-p', '--port',
        dest='port',
        type=_parse_ports,
        default=[1, 2]
    )
    parser.add_argument(
        '-f', '--file',
        dest='file'
    )
    parser.add_argument(
        '-u', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-s', '--use-interweaving',
        dest='use_interweaving',
        action='store_const',
        const=True,
        default=False
    )

    args = parser.parse_args(argv)

    ast = PARSER.parse(args.file)
    model = generate(
        ast,
        args.node,
        args.address,
        args.ports,
        interweaving=args.use_interweaving
    )

    if args.dump:
        pprint.pprint(model.to_json())

    else:
        if args.use_unix:
            fave = connect_to_fave(FAVE_DEFAULT_UNIX)
        else:
            fave = connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
        fave.setblocking(1)
        model_str = json.dumps(model.to_json())
        ret = fave_sendmsg(fave, model_str)
        if ret != None:
            raise Exception("ip6np was unable to send configuration correctly")

        fave.close()


if __name__ == "__main__":
    main(sys.argv[1:])
