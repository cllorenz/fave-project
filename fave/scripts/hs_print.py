#!/usr/bin/env python2

import sys
import json

from netplumber.vector import HeaderSpace

def print_help():
    print "usage: python2 hs_print <fave.json> <hs.txt>"


if __name__ == '__main__':
    argv = sys.argv[1:]

    if len(argv) != 2:
        print_help()
        sys.exit(1)

    mapping = json.load(open(argv[0], 'r'))['mapping']

    with open(argv[1], 'r') as f:
        hs_str = f.read()

    hs = HeaderSpace.from_str(hs_str)

    hs.pprint(mapping)
