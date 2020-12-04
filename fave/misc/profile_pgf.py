#!/usr/bin/env python2

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

import os
import sys
import logging

from ip6np import ip6np as ip6tables
import netplumber.dump_np as dumper


RULESET='bench/wl_up/rulesets/pgf-ruleset'
TMPFILE='/tmp/pgf-ruleset'

LOGGER = logging.getLogger("ad6")
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.DEBUG)

LOGGER.info("read ruleset")
ruleset = []
with open(RULESET, 'r') as rsf:
    ruleset = rsf.read().splitlines()

LOGGER.info("start run")
for no_rules in [len(ruleset)]: #range(3, len(ruleset), 10):
    rules = '\n'.join(ruleset[:no_rules])


    os.system("scripts/start_np.sh bench/wl_up/np.conf")
    os.system("scripts/start_aggr.sh")

    os.system('rm -f %s' % TMPFILE)
    with open(TMPFILE, 'w') as rsf:
        rsf.write(rules + '\n')

    LOGGER.info("try: %s", no_rules)
    #ip6tables.main(["-n", "pgf", "-p", 24, "-i", "2001:db8::1", "-f", TMPFILE])
    ip6tables.main(["-n", "pgf", "-p", 24, "-i", "2001:db8::1", "-f", RULESET])

    dumper.main(["-afnpt"])

    os.system("bash scripts/stop_fave.sh")


LOGGER.info("completed all rules")
