#!/usr/bin/env python2

""" This module generates the example workload's routes.
"""

import json

OFILE="bench/wl_tum/routes.json"

if __name__ == '__main__':
    routes = [
        # default route to the Internet
        ("fw.tum", 1, 65535, [], ["fd=fw.tum.1"], [])
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
