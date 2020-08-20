#!/usr/bin/env python2

""" This module generates the example workload's routes.
"""

import json

OFILE="bench/example/routes.json"

if __name__ == '__main__':
    routes = [
        # default route to the Internet
        ("fw.example.com", 1, 65535, [], ["fd=fw.example.com.1"], []),
        # route to dmz
        ("fw.example.com", 1, 0, ["ipv6_dst=2001:db8:2::0/64"], ["fd=fw.example.com.2"], []),
        ("fw.example.com", 1, 1, ["ipv6_dst=2001:db8:3::0/64"], ["fd=fw.example.com.3"], []),
        # dmz route to webserver
        ("dmz.example.com", 1, 0, ["ipv6_dst=2001:db8:2::0/64"], ["fd=dmz.example.com.3"], []),
        # dmz default route
        ("dmz.example.com", 1, 65535, [], ["fd=dmz.example.com.1"], [
            "dmz.example.com.2", "dmz.example.com.3"
        ]),
        # office route to office host
        ("office.example.com", 1, 0, ["ipv6_dst=2001:db8:2::0/64"], ["fd=dmz.example.com.3"], []),
        # office default route
        ("office.example.com", 1, 65535, [], ["fd=office.example.com.1"], [
            "office.example.com.2", "office.example.com.3"
        ]),
    ]

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
