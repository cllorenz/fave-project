#!/usr/bin/env python2

""" This module generates the example workload's topology.
"""

import json

OFILE="bench/wl_tum/topology.json"

if __name__ == '__main__':
    devices = [
#        ("fw.tum", "packet_filter", 2, "10.0.0.1", "bench/wl_tum/tum-ruleset"),
        ("fw.tum", "packet_filter", 2, "2001:db8::1", "bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset"),
        ("source.tum", "generator", [
            "tcp_src=10000;tcp_dst=80"
        ]),
    ]

    links = [
        ("source.tum.1", "fw.tum_forward_filter_in")
    ]

    example = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(example, indent=2))
