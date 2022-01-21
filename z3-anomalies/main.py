#!/usr/bin/env python3

import sys
import argparse

from parser.iptables import IP6TablesParser


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-r', '--ruleset',
        dest='ruleset',
        default='rulesets/tum-ruleset'
    )

    args = parser.parse_args(argv)

    with open(args.ruleset, 'r') as f:
        model = IP6TablesParser.parse(f.read())

    model.analyse('FORWARD')


if __name__ == '__main__':
    main(sys.argv[1:])
