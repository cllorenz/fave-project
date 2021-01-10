#!/usr/bin/env python2

""" This module generates the example workload's policies.
"""

import json

OFILE="bench/wl_tum/policies.json"

if __name__ == '__main__':
    probes = [
        ("probe.tum", "probe", "universal", None, None, None),
    ]


    links = [
        ("fw.tum.forward_filter_accept", "probe.tum.1")
    ]

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
