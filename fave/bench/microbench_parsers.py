#!/usr/bin/env python2

import time
import sys

from ip6np.parser import ASTParser as ANTLR
from misc.pyparsing_test import ASTParser as PYPARSING
from misc.pybison_test import IP6TablesParser as PYBISON

RULESET_FILE = 'bench/wl_ad6/rulesets/pgf-ruleset'

ROUND = lambda x: round(x, 4)

PARSERS = {
    'antlr' : ANTLR,
    'pyparsing' : PYPARSING(),
    'pybison' : PYBISON()
}

with open(RULESET_FILE, 'r') as rsf:
    ruleset = rsf.read()
    csv = []

    for pname in ['antlr', 'pyparsing', 'pybison']:
        parser = PARSERS[pname]
        meas = []

        print '\n%10s -' % pname,
        sys.stdout.flush()

        for i in range(10):
            start = time.time()

            if pname == 'pybison':
                parser.parse(RULESET_FILE)
            else:
                parser.parse(ruleset)

            end = time.time()
            dur = end - start

            meas.append(dur)
            print i,
            sys.stdout.flush()

        print ''

        mean = ROUND(reduce(lambda x, y: x + y, meas)/len(meas))
        median = ROUND(sorted(meas)[len(meas)/2])

        minimum = ROUND(min(meas))
        maximum = ROUND(max(meas))

        print '%10s - mean: %ss, median: %ss, min: %ss, max: %ss' % (
            pname, mean, median, minimum, maximum
        )
        csv.append((pname, mean, median, minimum, maximum))

    with open('parsers.csv', 'w') as csvf:
        csvf.write(
            '\n'.join([','.join([str(i) for i in line]) for line in csv]) + '\n'
        )
