#!/usr/bin/env python2

import os
import sys,getopt
import socket
import json
import netplumber.jsonrpc as jsonrpc

from aggregator.aggregator import UDS_ADDR

from util.print_util import eprint

def print_help():
    eprint(
        "dump_np -ahfnp -o <dir>",
        "\t-a dump fave aggregator",
        "\t-h print this help and exit",
        "\t-f dump flows",
        "\t-n dump plumbing network (tables, links, rules, policy)",
        "\t-o <dir> output directory (default: np_dump)",
        "\t-p dump pipes",
        sep="\n"
    )



def main(argv):
    try:
        opts,args = getopt.getopt(argv,"ahfno:p")
    except:
        print_help()
        sys.exit(2)

    use_fave = False
    use_flows = False
    use_network = False
    use_pipes = False

    odir = "np_dump"

    for opt,arg in opts:
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

        else:
            eprint("unknown option: %s, usage:" % opt)
            print_help()
            sys.exit(1)

    aggr = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    aggr.connect(UDS_ADDR)

    dump = {
        'type':'dump',
        'dir':odir,
        'fave':use_fave,
        'flows':use_flows,
        'network':use_network,
        'pipes':use_pipes
    }

    if any([use_fave,use_flows,use_network,use_pipes]):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

    aggr.sendall(json.dumps(dump))
    aggr.close()


if __name__ == '__main__':
    main(sys.argv[1:])
