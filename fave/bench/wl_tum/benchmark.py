#!/usr/bin/env python2

""" This module benchmarks FaVe using an example workload.
"""

import os
import sys
import json
import argparse
import logging

from util.bench_utils import create_topology, add_rulesets, add_routes, add_policies, add_sources

from bench.generic_benchmark import GenericBenchmark

class TUMBenchmark(GenericBenchmark):
    """ This class provides the TUM benchmark.
    """

    def _pre_preparation(self):
        if self.files['tum_ruleset'] == 'bench/wl_tum/rulesets/pgf.uni-potsdam.de-ruleset':
            ruleset = self.files['tum_ruleset']
            os.system("bash scripts/generate-pgf-ruleset.sh bench/wl_tum")
            os.system("sed -i 's/ -i / -i eth/g' %s" % ruleset)
            os.system("sed -i 's/ -o / -o eth/g' %s" % ruleset)


    def _post_preparation(self):
        os.system(
            "python2 bench/wl_tum/topogen.py %s %s" % (self.ip, self.files['tum_ruleset'])
        )


    def _compliance(self):
        self.logger.info("wait for fave")
        os.system("python2 misc/await_fave.py")
        self.logger.info("fave stopped successfully")


RULESET = 'bench/wl_tum/rulesets/tum-ruleset'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-v', '--verbose',
        dest='verbose',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-u', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-r', '--ruleset',
        dest='ruleset',
        default=RULESET
    )
    parser.add_argument(
        '-m', '--mapping',
        dest='mapping',
        default='bench/wl_tum/mapping.json'
    )
    parser.add_argument(
        '-4', '--ipv4',
        dest='ip',
        action='store_const',
        const='ipv4',
        default='ipv4'
    )
    parser.add_argument(
        '-6', '--ipv6',
        dest='ip',
        action='store_const',
        const='ipv6',
        default='ipv4'
    )
    parser.add_argument(
        '-n', '--no-interweaving',
        dest='use_interweaving',
        action='store_const',
        const=False,
        default=True
    )

    args = parser.parse_args(sys.argv[1:])

    length = json.load(open(args.mapping, 'r'))['length'] / 8

    files = {
        'tum_ruleset' : args.ruleset,
        'reach_csv' : 'bench/empty.csv',
        'inventory' : 'bench/empty.json',
    }

    TUMBenchmark(
        "bench/wl_tum",
        extra_files=files,
        length=length,
        ip=args.ip,
        use_unix=args.use_unix,
        use_interweaving=args.use_interweaving,
        mapping=args.mapping
    ).run()
