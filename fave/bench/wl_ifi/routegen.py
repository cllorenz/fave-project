#!/usr/bin/env python2

import json

OFILE="bench/wl_ifi/routes.json"

if __name__ == '__main__':
    routes = [
        ("ifi", 1, 0, ["ipv4_dst=10.0.13.0/23"], ["fd=ifi.18"], []),
        ("ifi", 1, 1, ["ipv4_dst=10.0.15.0/23"], ["fd=ifi.19"], []),
        ("ifi", 1, 2, ["ipv4_dst=10.0.17.0/23"], ["fd=ifi.20"], []),
        ("ifi", 1, 3, ["ipv4_dst=10.0.19.0/23"], ["fd=ifi.21"], []),
        ("ifi", 1, 4, ["ipv4_dst=10.0.21.0/23"], ["fd=ifi.22"], []),
        ("ifi", 1, 5, ["ipv4_dst=10.0.23.0/23"], ["fd=ifi.23"], []),
        ("ifi", 1, 6, ["ipv4_dst=10.0.25.0/23"], ["fd=ifi.24"], []),
        ("ifi", 1, 7, ["ipv4_dst=10.0.27.0/23"], ["fd=ifi.25"], []),
        ("ifi", 1, 8, ["ipv4_dst=10.0.29.0/23"], ["fd=ifi.26"], []),
        ("ifi", 1, 9, ["ipv4_dst=10.0.31.0/23"], ["fd=ifi.27"], []),
        ("ifi", 1, 65535, [], ["fd=ifi.17"], [])
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
