#!/usr/bin/env python2

""" This module generates the example workload's routes.
"""

import json

OFILE="bench/wl_generic_fw/routes.json"

if __name__ == '__main__':
    routes = []

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
