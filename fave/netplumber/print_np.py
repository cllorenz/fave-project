#!/usr/bin/env python2

import sys,getopt
import socket
import netplumber.jsonrpc as jsonrpc

from util.print_util import eprint

def print_help():
    eprint(
        "print_np -hsutn",
        "\t-h print this help and exit",
        "\t-n print net_plumber network",
        "\t-t print the topology",
        "\t-s connect to net_plumber via tcp (ip=127.0.0.1, port=1234)",
        "\t-u connect to net_plumber via unix socket (/tmp/net_plumber.socket)",
        sep="\n"
    )



if __name__ == '__main__':
    try:
        opts,args = getopt.getopt(sys.argv[1:],"htnsu")
    except:
        print_help()
        sys.exit(2)

    use_tcp = True
    use_unix = False
    print_topo = False
    print_nw = False

    for opt,arg in opts:
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
        np = (server,port)
        sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        sock.connect(np)

    elif use_unix:
        sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        sock.connect("/tmp/net_plumber.socket")

    else:
        print_help()
        sys.exit(3)

    server = "127.0.0.1"
    port = 1234


    if print_topo:
        jsonrpc.print_topology(sock)

    if print_nw:
        jsonrpc.print_plumbing_network(sock)

    sock.close()

    sys.exit(0)
