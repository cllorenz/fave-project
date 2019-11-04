#!/usr/bin/env python2

""" This module generates the IFI workload's policies.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

IFILE="bench/wl_ifi/inventory.json"
OFILE="bench/wl_ifi/policies.json"

if __name__ == '__main__':
    with open(IFILE, 'r') as inv_file:
        inventory = json.load(inv_file)

    domain_to_ports = inventory["domain_to_ports"]

    probes = [
        ("probe.Internet", "probe", "universal", None, None, ["(p in (ifi.18))"]),
        ("probe.external.ifi", "probe", "universal", None, None, [".*(p=ifi.19);$"])
    ]

    out_port = lambda _ip, op: op
    probes.extend([
        (
            "probe.%s" % sub,
            "probe",
            "existential",
            None,
            None,
            [".*(p=ifi.%s);$" % out_port(*domain_to_ports[sub])]
        ) for sub in SUBNETS
    ])

    links = [
        ("ifi.18", "probe.Internet.1"),
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
