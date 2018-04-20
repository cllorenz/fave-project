#!/usr/bin/env python2

#!/usr/bin/env python2

import os
import sys,getopt
import socket
import json
import netplumber.jsonrpc as jsonrpc

from util.print_util import eprint

def print_help():
    eprint(
        "print_np -hfnptn -o <dir>",
        "\t-h print this help and exit",
        "\t-f dump flows",
        "\t-n dump plumbing network (tables, links, rules, policy)",
        "\t-o <dir> output directory (default: np_dump)",
        "\t-p dump pipes",
        "\t-s connect to net_plumber via tcp (ip=127.0.0.1, port=1234)",
        "\t-u connect to net_plumber via unix socket (/tmp/net_plumber.socket)",
        sep="\n"
    )



def main(argv):
    try:
        opts,args = getopt.getopt(argv,"hfno:psu")
    except:
        print_help()
        sys.exit(2)

    use_tcp = True
    use_unix = False

    use_flows = False
    use_network = False
    use_pipes = False

    odir = "np_dump"

    for opt,arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)

        elif opt == '-s':
            use_tcp = True
            use_unix = False
            np = ("127.0.0.1",1234)

        elif opt == '-u':
            use_tcp = False
            use_unix = True
            np = "/tmp/net_plumber.socket"

        elif opt == '-f':
            use_flows = True

        elif opt == '-n':
            use_network = True

        elif opt == '-p':
            use_pipes = True

        elif opt == '-o':
            odir = arg

        else:
            print_help()
            sys.exit(1)

    if use_tcp:
        sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        sock.connect(np)

    elif use_unix:
        sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        sock.connect(np)

    else:
        print_help()
        sys.exit(3)

    if any([use_flows,use_network,use_pipes]):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

    if use_flows:
        jsonrpc.dump_flows(sock,odir)

    if use_network:
        jsonrpc.dump_plumbing_network(sock,odir)

    if use_pipes:
        jsonrpc.dump_pipes(sock,odir)

    sock.close()

if __name__ == '__main__':
    main(sys.argv[1:])
