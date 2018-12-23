#!/usr/bin/env python2

import json

OFILE="bench/wl-ifi/policies.json"

if __name__ == '__main__':
    probes = [
        ("probe.internet", "probe", "universal", None, None, ["(p in (ifi.13))"]),
        ("probe.ifi", "probe", "existential", None, None, [".*(p=ifi.14);$"])
    ]
    links = [
        ("ifi.13", "probe.internet.1"),
        ("ifi.14", "probe.ifi.1")
    ]

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
