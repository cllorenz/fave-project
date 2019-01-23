#!/usr/bin/env python2

import json

OFILE="bench/wl_ifi/policies.json"

if __name__ == '__main__':
    probes = [
        ("probe.proxy.uni-potsdam.de", "probe", "universal", None, None, ["(p in (ifi.17))"]),
        ("probe.internal.ifi", "probe", "existential", None, None, [".*(p=ifi.18);$"]),
        ("probe.admin.ifi", "probe", "existential", None, None, [".*(p=ifi.19);$"]),
        ("probe.office.ifi", "probe", "existential", None, None, [".*(p=ifi.20);$"]),
        ("probe.staff-1.ifi", "probe", "existential", None, None, [".*(p=ifi.21);$"]),
        ("probe.staff-2.ifi", "probe", "existential", None, None, [".*(p=ifi.22);$"]),
        ("probe.pool.ifi", "probe", "existential", None, None, [".*(p=ifi.23);$"]),
        ("probe.lab.ifi", "probe", "existential", None, None, [".*(p=ifi.24);$"]),
        ("probe.hpc-mgt.ifi", "probe", "existential", None, None, [".*(p=ifi.25);$"]),
        ("probe.hpc-ic.ifi", "probe", "existential", None, None, [".*(p=ifi.26);$"]),
        ("probe.slb.ifi", "probe", "existential", None, None, [".*(p=ifi.27);$"]),
        ("probe.mgt.ifi", "probe", "existential", None, None, [".*(p=ifi.28);$"]),
        ("probe.san.ifi", "probe", "existential", None, None, [".*(p=ifi.29);$"]),
        ("probe.vmo.ifi", "probe", "existential", None, None, [".*(p=ifi.30);$"]),
        ("probe.prt.ifi", "probe", "existential", None, None, [".*(p=ifi.31);$"]),
        ("probe.cam.ifi", "probe", "existential", None, None, [".*(p=ifi.32);$"])
    ]
    links = [
        ("ifi.17", "probe.proxy.uni-potsdam.de.1"),
        ("ifi.18", "probe.internal.ifi.1"),
        ("ifi.19", "probe.admin.ifi.1"),
        ("ifi.20", "probe.office.ifi.1"),
        ("ifi.21", "probe.staff-1.ifi.1"),
        ("ifi.22", "probe.staff-2.ifi.1"),
        ("ifi.23", "probe.pool.ifi.1"),
        ("ifi.24", "probe.lab.ifi.1"),
        ("ifi.25", "probe.hpc-mgt.ifi.1"),
        ("ifi.26", "probe.hpc-ic.ifi.1"),
        ("ifi.27", "probe.slb.ifi.1"),
        ("ifi.28", "probe.mgt.ifi.1"),
        ("ifi.29", "probe.san.ifi.1"),
        ("ifi.30", "probe.vmo.ifi.1"),
        ("ifi.31", "probe.prt.ifi.1"),
        ("ifi.32", "probe.cam.ifi.1")
    ]

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
