#!/usr/bin/env python2

""" This module provides functionality to let FaVe dump its state.
"""

import os
import sys
import getopt
import socket
import json

from filelock import FileLock

from aggregator.aggregator import UDS_ADDR

from util.print_util import eprint

def print_help():
    """ Prints usage message to stderr.
    """

    eprint(
        "dump_np -ahfnp -o <dir>",
        "\t-a dump fave aggregator",
        "\t-h print this help and exit",
        "\t-f dump flows",
        "\t-n dump plumbing network (tables, links, rules, policy)",
        "\t-o <dir> output directory (default: np_dump)",
        "\t-p dump pipes",
        "\t-t dump flow trees",
        sep="\n"
    )



def main(argv):
    """ Sends an event to FaVe to dump its state.
    """

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "ahfno:pt"))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    use_fave = False
    use_flows = False
    use_network = False
    use_pipes = False
    use_trees = False

    odir = "np_dump"

    for opt, arg in opts:
        if opt == '-h':
            eprint("usage:")
            print_help()
            sys.exit(0)

        elif opt == '-a':
            use_fave = True

        elif opt == '-f':
            use_flows = True

        elif opt == '-n':
            use_network = True

        elif opt == '-p':
            use_pipes = True

        elif opt == '-o':
            odir = arg

        elif opt == '-t':
            use_trees = True

        else:
            eprint("unknown option: %s, usage:" % opt)
            print_help()
            sys.exit(1)

    aggr = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    aggr.connect(UDS_ADDR)

    dump = {
        'type':'dump',
        'dir':odir,
        'fave':use_fave,
        'flows':use_flows,
        'network':use_network,
        'pipes':use_pipes,
        'trees':use_trees
    }

    if any([use_fave, use_flows, use_network, use_pipes, use_trees]):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

    lock = FileLock("%s/.lock" % odir)
    lock.acquire()

    aggr.sendall(json.dumps(dump))
    aggr.close()


if __name__ == '__main__':
    main(sys.argv[1:])
