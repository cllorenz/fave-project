#!/usr/bin/env python2

""" This module generates the generic workload's topology.
"""

import json
import sys
import os

TOPOLOGY="bench/wl_generic_fw/topology.json"
SOURCES="bench/wl_generic_fw/sources.json"
ROLES="bench/wl_generic_fw/roles.json"
INTERFACES="bench/wl_generic_fw/interfaces.json"

_TAGS = {
    'ipv4' : 'packet.ipv4.source',
    'ipv6' : 'packet.ipv6.source',
    'vlan' : 'packet.ether.vlan',
    'interface' : 'in_port'
}

def _attributes_to_fields(attributes):
    res = []
    for name, value in {k:v for k, v in attributes.iteritems() if k not in [
        "description", "hosts", "gateway", "gateway4", "gateway6"
    ]}.iteritems():
        res.append("%s=%s" % (_TAGS[name], value+'_ingress' if name == 'interface' else value))

    return res


def _port_field_for_role(role, interfaces):
    return [
        'in_port=' + (
            'fw.generic.%s_ingress' % interfaces[
                'external'
            ] if role[
                'name'
            ] == 'Internet' else 'fw.generic.%s_ingress' % interfaces[
                'internal'
            ]
        )
    ]


if __name__ == '__main__':
    address = "2001:db8::1"
    ruleset = "bench/wl_generic_fw/default/ruleset"
    if len(sys.argv) == 3:
        address = "2001:db8::1" if sys.argv[1] == "ipv6" else "10.0.0.1"
        ruleset = sys.argv[2]

    interfaces = json.load(open(INTERFACES, "r"))

    devices = [
        ("fw.generic", "packet_filter", sorted(interfaces.values()), address, ruleset)
    ]

    links = []

    roles = json.load(open(ROLES, 'r'))

    sources = [
        (
            "source.%s" % role['name'],
            "generator",
            _attributes_to_fields(role['attributes']) + _port_field_for_role(role, interfaces)
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
