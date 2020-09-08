#!/usr/bin/env python2

""" This module generates the example workload's topology.
"""

import json

TOPOLOGY="bench/wl_tum/topology.json"
SOURCES="bench/wl_tum/sources.json"

if __name__ == '__main__':
    devices = [
#        ("fw.tum", "packet_filter", 2, "10.0.0.1", "bench/wl_tum/tum-ruleset"),
        ("fw.tum", "packet_filter", 2, "2001:db8::1", "bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset")
    ]

    links = []

    sources = [
        ("source.tum", "generator", [
            "tcp_src=10000;tcp_dst=80"
        ])
    ]

    source_links = [
        ("source.tum.1", "fw.tum_forward_filter_in")
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
