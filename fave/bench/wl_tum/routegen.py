#!/usr/bin/env python2

""" This module generates the example workload's routes.
"""

import json

OFILE="bench/wl_tum/routes.json"

if __name__ == '__main__':
    routes = [
        # default route to the Internet
        ("fw.tum", 1, 65535, [], ["fd=fw.tum.1"], [])
#        ("fw.tum", 1, 1, ["ipv4_dst=128.0.0.0/2"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=130.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=131.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=132.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=136.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=138.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=144.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=148.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=160.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=176.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=184.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=185.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=186.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=188.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=189.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=190.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=192.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=193.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=194.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=196.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=200.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=208.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=224.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=45.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=80.0.0.0/8"], ["fd=fw.tum.2"], []),
#        ("fw.tum", 1, 1, ["ipv4_dst=81.0.0.0/8"], ["fd=fw.tum.2"], [])
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
