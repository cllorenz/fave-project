#!/usr/bin/env python2

import json

OFILE="bench/wl_example/routes.json"

if __name__ == '__main__':
    # route: (name, table, idx, [fields], [commands])
    routes = [
        # pgf -> dmz
        ("pgf", 1, 0, ["ipv6_dst=2001:db8::100/120"], ["fd=pgf.2"], []),
        # pgf -> office
        ("pgf", 1, 1, ["ipv6_dst=2001:db8::200/120"], ["fd=pgf.3"], []),
        # pgf -> internet
        ("pgf", 1, 65535, [], ["fd=pgf.1"], []),
        # dmz -> dmz
        ("dmz", 1, 0, ["ipv6_dst=2001:db8::100/120"], ["fd=dmz.2"], ["dmz.1"]),
        # dmz -> pgf
        ("dmz", 1, 65535, [], ["fd=dmz.1"], ["dmz.2"]),
        # office -> office
        ("office", 1, 0, ["ipv6_dst=2001:db8::200/120"], ["fd=office.2"], ["office.1"]),
        # office -> pgf
        ("office", 1, 65535, [], ["fd=office.1"], ["office.2"])
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
