#!/usr/bin/env python2

""" This module generates the IFI workload's policies.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

IFILE="bench/wl_ifi/inventory.json"
REACH_JSON="bench/wl_ifi/reachable.json"
OFILE="bench/wl_ifi/policies.json"

if __name__ == '__main__':
    with open(IFILE, 'r') as inv_file:
        inventory = json.load(inv_file)

    with open(REACH_JSON, 'r') as reach_file:
        reachable = json.load(reach_file)

    domain_to_ports = inventory["domain_to_ports"]

    probes = [
        ("probe.Internet", "probe", "universal", None, None, None, [
            ".*(p in (admin.ifi.2,external.ifi.2,lab.ifi.2,office.ifi.2,pool.ifi.2,staff_1.ifi.2,staff_2.ifi.2))$"
        ]),
        ("probe.external.ifi", "probe", "universal", None, None, None, [
            ".*(p in (ifi.1,admin.ifi.2,external.ifi.2,lab.ifi.2,office.ifi.2,pool.ifi.2,slb.ifi.2,staff_1.ifi.2,staff_2.ifi.2))$"
        ])
    ]

    probes.extend([
        (
            "probe.%s" % sub,
            "probe",
            "universal",
            None,
            None,
            None,
            [".*(p in (%s))$" % ','.join(
                [("%s.2" % s) if s != "Internet" else "ifi.1" for s in reachable[sub]]
            )]
        ) for sub in SUBNETS
    ])

    links = [
        ("ifi.1", "probe.Internet.1"),
        ("external.ifi.3", "probe.external.ifi.1")
    ]

    links.extend([
        ("%s.3" % sub, "probe.%s.1" % sub) for sub in SUBNETS
    ])

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
