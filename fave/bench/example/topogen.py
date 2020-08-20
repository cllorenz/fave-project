#!/usr/bin/env python2

""" This module generates the example workload's topology.
"""

import json

OFILE="bench/example/topology.json"

if __name__ == '__main__':
    # device: (name, type, no_ports, acls)
    devices = [
        # central firewall with 3 ports
        ("fw.example.com", "packet_filter", 3, "2001:db8::1", "bench/example/ruleset"),
        # a generator representing the Internet
        ("source.Internet", "generator", ["ipv6_src=0::0/0"]),
        # switches of the subnet for dmz and office services
        ("dmz.example.com", "switch", 3),
        ("office.example.com", "switch", 3),
        # generators representing dmz and office hosts
        ("source.dmz.example.com", "generator", [
            "ipv6_src=2001:db8:2::0/64"
        ]),
        ("source.office.example.com", "generator", [
            "ipv6_src=2001:db8:3::0/64"
        ])
    ]

    links = [
        # internet --> firewall
        ("source.Internet.1", "fw.example.com.1"),
        # firewall <-> dmz
        ("dmz.example.com.1", "fw.example.com.2"),
        ("fw.example.com.5", "dmz.example.com.1"),
        # firewall <-> office
        ("office.example.com.1", "fw.example.com.3"),
        ("fw.example.com.6", "office.example.com.1"),
        # webserver --> dmz
        ("source.dmz.example.com.1", "dmz.example.com.2"),
        # office host --> office
        ("source.office.example.com.1", "office.example.com.2")
    ]

    example = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(example, indent=2))
