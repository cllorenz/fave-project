#!/usr/bin/env python2

import json

OFILE="bench/wl_ifi/routes.json"

if __name__ == '__main__':
    routes = [
        ("ifi", 1, 0, ["ipv4_dst=10.0.13.0/23"], ["fd=ifi.14"]),
        ("ifi", 1, 65535, [], ["fd=ifi.13"])
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
