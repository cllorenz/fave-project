#!/usr/bin/env python2

""" This module generates the example workload's topology.
"""

import json
import sys

TOPOLOGY="bench/wl_tum/topology.json"
SOURCES="bench/wl_tum/sources.json"

if __name__ == '__main__':
    address = "2001:db8::1"
    ruleset = "bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset"
    if len(sys.argv) == 3:
        address = "2001:db8::1" if sys.argv[1] == "ipv6" else "10.0.0.1"
        ruleset = sys.argv[2]

    devices = [
        ("fw.tum", "packet_filter", ['eth0', 'eth1'], address, ruleset)
    ]

    links = []

    sources = [
        ("source.tum", "generator", [
            "tcp_src=10000;tcp_dst=80"
        ])
    ]

    source_links = [
        ("source.tum.1", "fw.tum.forward_filter_in", True)
    ]

    topology = {
        'devices' : devices,
        'links' : links
    }

    sources = {
        'devices' : sources,
        'links' : source_links
    }

    json.dump(topology, open(TOPOLOGY, 'w'), indent=2)
    json.dump(sources, open(SOURCES, 'w'), indent=2)
