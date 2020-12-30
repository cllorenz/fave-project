#!/usr/bin/env python2

""" This module generates the example workload's routes.
"""

import json

OFILE="bench/wl_generic_fw/routes.json"

if __name__ == '__main__':
    routes = [
        # default route to the Internet
        ("fw.generic", 1, 65535, [], ["fd=fw.generic.1"], [])
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
