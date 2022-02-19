#!/usr/bin/env python3

import sys
import argparse
import time

from parser.iptables import IP6TablesParser


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-r', '--ruleset',
        dest='ruleset',
        default='rulesets/tum-ruleset'
    )
    parser.add_argument(
        '-m', '--measure',
        action='store_const',
        dest='measure',
        const=True,
        default=False
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_const',
        dest='verbose',
        const=True,
        default=False
    )

    args = parser.parse_args(argv)

    with open(args.ruleset, 'r') as f:
        raw = f.read()

        if args.measure:
            t_start = time.time()

        model = IP6TablesParser.parse(raw)

        if args.measure:
            t_end = time.time()
            print("Parsing took {:.4f} seconds.".format(t_end - t_start))

    if args.measure:
        t_start = time.time()

    model.analyse('FORWARD', verbose=args.verbose)

    if args.measure:
        t_end = time.time()
        print("Analysis took {:.4f} seconds.".format(t_end - t_start))


if __name__ == '__main__':
    main(sys.argv[1:])
