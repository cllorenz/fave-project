#!/usr/bin/env python2

""" This module generates the IFI workload's policies.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

OFILE="bench/wl_ifi/policies.json"

if __name__ == '__main__':
    probes = [
        ("probe.proxy.uni-potsdam.de", "probe", "universal", None, None, ["(p in (ifi.17))"])
    ]

    probes.extend([
        (
            "probe.%s.ifi" % sub,
            "probe",
            "existential",
            None,
            None,
            [".*(p=ifi.%s);$" % str(idx+18)]
        ) for idx, sub in enumerate(SUBNETS)
    ])

    links = [
        ("ifi.17", "probe.proxy.uni-potsdam.de.1")
    ]

    links.extend([
        ("%s.ifi.3" % sub, "probe.%s.ifi.1" % sub) for sub in SUBNETS
    ])

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
