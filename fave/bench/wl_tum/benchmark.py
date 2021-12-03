#!/usr/bin/env python2

""" This module benchmarks FaVe using an example workload.
"""

import os
import sys
import json
import getopt
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

    verbose = False
    ip = 'ipv4'
    ruleset = RULESET
    mapping = 'bench/wl_tum/mapping.json'

    use_unix = True

    try:
        opts, args = getopt.getopt(sys.argv[1:], "vm:r:46")
    except getopt.GetoptError as err:
        print err
        sys.exit(1)

    for opt, arg in opts:
        if opt == '-v':
            verbose = True
        if opt == '-r':
            ruleset = arg
        if opt == '-4':
            ip = 'ipv4'
        if opt == '-6':
            ip = 'ipv6'
        if opt == '-m':
            mapping = arg

    length = json.load(open(mapping, 'r'))['length'] / 8

    files = {
        'tum_ruleset' : ruleset
    }

    TUMBenchmark("bench/wl_tum", extra_files=files, length=length, ip=ip).run()
