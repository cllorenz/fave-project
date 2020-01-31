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

    fave = json.load(open(argv[0], 'r'))
    mapping = fave['mapping']

    with open(argv[1], 'r') as f:
        rule_str = f.read()

    _at, rno_str, _arrow = rule_str.rstrip().split(' ')

    rno = int(rno_str, 16)
    tno = fave['id_to_rule'][str(rno)]

    table = fave['id_to_table'][str(tno)]

    print "\n@ %s.%s <--\n" % (table, rno & 0xffff)
