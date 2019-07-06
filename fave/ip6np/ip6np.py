#!/usr/bin/env python2

""" This module provides functionality to send ip6tables configurations to FaVe.
"""

import sys
import getopt
import json
import socket
import pprint

import generator

from misc.pybison_test import IP6TablesParser
from util.print_util import eprint
from util.aggregator_utils import UDS_ADDR

def print_help():
    """ Prints the usage on stderr.
    """

    eprint(
        "ip6np -n <node> -p <ports> -f <file>",
        "\t-d dump model",
        "\t-n <node> node identifier",
        "\t-i <ip> ip address",
        "\t-p <ports> number of ports",
        "\t-f <file> ip6tables ruleset",
        sep="\n"
    )


def main(argv):
    """ Connects to FaVe and sends an ip6tables configuration event.
    """

    ifile = ''
    node = ''
    ports = [1, 2]
    dump = False

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "hdn:i:p:f:", ["node=", "file="]))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)
        elif opt == '-n':
            node = arg
        elif opt == '-i':
            address = arg
        elif opt == '-p':
            ports = range(1, int(arg)+1)
        elif opt == '-f':
            ifile = arg
        elif opt == '-d':
            dump = True

    parser = IP6TablesParser()
    ast = parser.parse(ifile)

    model = generator.generate(ast, node, address, ports)

    if dump:
        pprint.pprint(model.to_json())

    else:
        aggr = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        aggr.connect(UDS_ADDR)

        aggr.send(json.dumps(model.to_json()))

        aggr.close()


if __name__ == "__main__":
    main(sys.argv[1:])
