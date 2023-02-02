#!/usr/bin/env python3

""" This module generates the shadowing workload's topology.
"""

import json
import sys
import os

TOPOLOGY="bench/wl_shadow/topology.json"

_TAGS = {
    'ipv4' : 'packet.ipv4.source',
    'ipv6' : 'packet.ipv6.source',
    'vlan' : 'packet.ether.svlan',
    'interface' : 'in_port'
}


if __name__ == '__main__':
    address = "2001:db8::1"
    ruleset = "bench/wl_shadow/rules.ipt"
    if len(sys.argv) == 3:
        address = "2001:db8::1" if sys.argv[1] == "ipv6" else "10.0.0.1"
        ruleset = sys.argv[2]

    devices = [
        ("fw.shadow", "packet_filter", ['eth0', 'eth1'], address, ruleset)
    ]

    links = []

    topology = {
        'devices' : devices,
        'links' : links
    }

    json.dump(topology, open(TOPOLOGY, 'w'), indent=2)
