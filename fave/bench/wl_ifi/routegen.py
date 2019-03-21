#!/usr/bin/env python2

""" This module generates the IFI workload's routes.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

OFILE="bench/wl_ifi/routes.json"

if __name__ == '__main__':
    routes = [
        ("ifi", 1, 65535, [], ["fd=ifi.17"], [])
    ]

    routes.extend([
        (
            "ifi", 1, idx,
            ["ipv4_dst=10.0.%s.0/23" % str((idx+6)*2+1)],
            ["fd=ifi.%s" % str(idx+18)],
            []
        ) for idx, sub in enumerate(SUBNETS)
    ])


    routes.extend([
        (
            "%s.ifi" % sub, 1, 0,
            ["ipv4_dst=10.0.%s.0/23" % str((idx+6)*2+1)],
            ["fd=%s.ifi.3" % sub],
            []
        ) for idx, sub in enumerate(SUBNETS)
    ])

    routes.extend([
        (
            "%s.ifi" % sub, 1, 65535, [], ["fd=%s.ifi.1" % sub], []
        ) for sub in SUBNETS
    ])


    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
