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

""" RETIRED (2026-10-08). Which ip6tables parser is fastest?

Written 2019-06-19 to compare three parsing approaches for an ip6tables rule
set -- ANTLR, pyparsing and pybison -- over ten runs each on wl_up's
pgf.uni-potsdam.de ruleset, reporting mean and median.

**pybison won, and that answer is still in force.** FaVe's production ip6tables
parser is `iptables/parser.py`, `IP6TablesParser(BisonParser)` -- "a fast parser
for ip6tables rule sets based on GNU Flex and Bison". The cost of that choice is
still being paid deliberately: `fave/setup.sh` builds `pybison==0.6.4` from
source because the prebuilt cp312 wheel segfaults, and the Dockerfile installs
`bison` and `m4` for it. So this file is the record of why FaVe carries that
dependency.

**It does not run, and has not since 2021.** It is kept for the comparison, not
as a harness. Its three imports all name modules from the old layout:

  - `ip6np.parser` -- the ANTLR parser, since removed; nothing in the tree
    mentions ANTLR any more except this file;
  - `models.iptables.pybison_singleton` -- moved out from under `models/` in
    a8c92343 (2021-08-13); today's equivalent is `iptables/parser.py`;
  - `misc.pyparsing_test` -- deleted in 5f6e697b (2021-12-03).

There is also a Python-2 residue that 2to3 did not catch: `len(meas)/2` below
is true division, so the median index is a float and would raise TypeError.
The 2023-02-02 python3 migration ran over a file that had already been
unrunnable for eighteen months -- the clearest evidence that nothing invoked it
in between.
"""

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
