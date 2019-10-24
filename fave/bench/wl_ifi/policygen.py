#!/usr/bin/env python2

""" This module generates the IFI workload's policies.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

OFILE="bench/wl_ifi/policies.json"

if __name__ == '__main__':
    probes = [
        ("probe.Internet", "probe", "universal", None, None, ["(p in (ifi.18))"]),
        ("probe.external.ifi", "probe", "universal", None, None, [".*(p=ifi.19);$"])
    ]

    probes.extend([
        (
            "probe.%s" % sub,
            "probe",
            "existential",
            None,
            None,
            [".*(p=ifi.%s);$" % str(idx+20)]
        ) for idx, sub in enumerate(SUBNETS)
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
