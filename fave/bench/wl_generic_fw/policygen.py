#!/usr/bin/env python2

""" This module generates the example workload's policies.
"""

import json

ROLES="bench/wl_generic_fw/roles.json"
INTERFACES="bench/wl_generic_fw/interfaces.json"
OFILE="bench/wl_generic_fw/policies.json"


_TAGS = {
    'ipv4' : 'packet.ipv4.destination',
    'ipv6' : 'packet.ipv6.destination',
    'vlan' : 'packet.ether.dvlan',
    'interface' : 'out_port'
}

def _attributes_to_fields(attributes):
    res = []
    for name, value in {k:v for k, v in attributes.iteritems() if k not in [
        "description", "hosts", "gateway", "gateway4", "gateway6"
    ]}.iteritems():
        res.append("%s=%s" % (_TAGS[name], value+'_egress' if name == 'interface' else value))

    return res


def _port_field_for_role(role, interfaces):
    return [
        'out_port=' + (
            'fw.generic.%s_egress' % interfaces[
                'external'
            ] if role[
                'name'
            ] == 'Internet' else 'fw.generic.%s_egress' % interfaces[
                'internal'
            ]
        )
    ]


if __name__ == '__main__':
    roles = json.load(open(ROLES, 'r'))

    interfaces = json.load(open(INTERFACES, 'r'))

    probes = [
        (
            "probe.%s" % role['name'],
            "probe",
            "universal",
            _attributes_to_fields(role['attributes']) + _port_field_for_role(role, interfaces),
            None,
            None,
            None
        ) for role in roles
    ]


    links = [
        (
            "fw.generic.forward_filter_accept", "probe.%s.1" % role['name'], False
        ) for role in roles
    ]

    policies = {
        "devices" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
