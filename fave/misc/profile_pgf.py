#!/usr/bin/env python2

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
    ruleset = rsf.read().split('\n')

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
