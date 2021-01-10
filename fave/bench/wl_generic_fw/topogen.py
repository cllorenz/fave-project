#!/usr/bin/env python2

""" This module generates the generic workload's topology.
"""

import json
import sys

TOPOLOGY="bench/wl_generic_fw/topology.json"
SOURCES="bench/wl_generic_fw/sources.json"
ROLES="bench/wl_generic_fw/roles.json"

_TAGS = {
    'ipv4' : 'packet.ipv4.source',
    'ipv6' : 'packet.ipv6.source',
    'vlan' : 'packet.ether.vlan'
}

def _attributes_to_fields(attributes):
    res = []
    for name, value in {k:v for k, v in attributes.iteritems() if k not in [
        "description", "hosts", "gateway", "gateway4", "gateway6"
    ]}.iteritems():
        res.append("%s=%s" % (_TAGS[name], value))

    return res


if __name__ == '__main__':
    address = "2001:db8::1"
    ruleset = "bench/wl_generic_fw/default/ruleset"
    if len(sys.argv) == 3:
        address = "2001:db8::1" if sys.argv[1] == "ipv6" else "10.0.0.1"
        ruleset = sys.argv[2]

    devices = [
        ("fw.generic", "packet_filter", 1, address, ruleset)
    ]

    links = []

    roles = json.load(open(ROLES, 'r'))

    sources = [
        (
            "source.%s" % role['name'],
            "generator",
            _attributes_to_fields(role['attributes'])
        ) for role in roles
    ]

    source_links = [
        (
            "source.%s.1" % role['name'],
            "fw.generic.forward_filter_in"
        ) for role in roles
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
