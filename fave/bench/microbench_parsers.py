#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

import time
import sys

from ip6np.parser import ASTParser as ANTLR
from misc.pyparsing_test import ASTParser as PYPARSING
from models.iptables.pybison_singleton import PARSER as PYBISON
from functools import reduce

RULESET_FILE = 'bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset'

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

        print('\n%10s -' % pname, end=' ')
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
            print(i, end=' ')
            sys.stdout.flush()

        print('')

        mean = ROUND(reduce(lambda x, y: x + y, meas)/len(meas))
        median = ROUND(sorted(meas)[len(meas)/2])

        minimum = ROUND(min(meas))
        maximum = ROUND(max(meas))

        print('%10s - mean: %ss, median: %ss, min: %ss, max: %ss' % (
            pname, mean, median, minimum, maximum
        ))
        csv.append((pname, mean, median, minimum, maximum))

    with open('parsers.csv', 'w') as csvf:
        csvf.write(
            '\n'.join([','.join([str(i) for i in line]) for line in csv]) + '\n'
        )
