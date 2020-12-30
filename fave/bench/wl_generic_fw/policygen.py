#!/usr/bin/env python2

""" This module generates the example workload's policies.
"""

import json

ROLES="bench/wl_generic_fw/roles.json"
OFILE="bench/wl_generic_fw/policies.json"

if __name__ == '__main__':
    roles = json.load(open(ROLES, 'r'))

    probes = [
        (
            "probe.%s" % role['name'], "probe", "universal", None, None, None
        ) for role in roles
    ]


    links = [
        (
            "fw.generic_forward_filter_accept", "probe.%s.1" % role['name']
        ) for role in roles
    ]

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
