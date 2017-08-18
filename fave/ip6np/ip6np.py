#!/usr/bin/env python2
import sys, getopt

# uncomment if pypy is used
#sys.path.append("/usr/lib/python2.7/site-packages")

from parser import ASTParser
import generator

#import time
import json

import socket

from util.print_util import eprint

def print_help():
    eprint("ip6np -n <node> -p <ports> -f <file>",
        "\t-n <node> node identifier",
        "\t-i <ip> ip address",
        "\t-p <ports> number of ports"
        "\t-f <file> ip6tables ruleset",
        sep="\n"
    )

def main(argv):
    ifile = ''
    node = ''
    ports = [1,2]

    try:
        opts,args = getopt.getopt(argv,"hn:i:p:f:",["node=","file="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    for opt,arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)
        elif opt == '-n':
            node = arg
        elif opt == '-i':
            address = arg
        elif opt == '-p':
            ports = range(1,int(arg))
        elif opt == '-f':
            ifile = arg

#    eprint("Input file is", ifile, sep=" ")

#    t1 = time.time()
    with open(ifile,'r') as f:
        ruleset = f.read()

#    t2 = time.time()

    if ruleset:
        ast = ASTParser.parse(ruleset)

#        t3 = time.time()

        model = generator.generate(ast,node,address,ports)

#        t4 = time.time()

#        td1 = t2-t1
#        td2 = t3-t2
#        td3 = t4-t3
#        res = td1+td2+td3

        aggr = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        aggr.connect("/tmp/np_aggregator.socket")

        aggr.send(json.dumps(model.to_json()))

        aggr.close()

        #print(json.dumps(json.loads(model),indent=2,sort_keys=True))
#        print("file reading: %s\nparsing: %s\nmodel generation: %s\ntotal: %s" % (str(td1),str(td2),str(td3),str(res)))

if __name__ == "__main__":
    main(sys.argv[1:])
