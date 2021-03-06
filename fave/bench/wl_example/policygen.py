#!/usr/bin/env python2

import json

POLICIES="bench/wl_example/policies.json"

if __name__ == '__main__':
    # probe: (name, type, quantor, [filter_fields], [test_fields], [test_path])
    probes = [
        ("probe.internet", "probe", "universal", None, None, None, ["(p in (pgf.1))"]),
        ("probe.dmz", "probe", "existential", None, None, None, [".*(p=pgf.1);$"]),
        ("probe.office", "probe", "existential", None, None, None, [".*(p=pgf.1);$"])
    ]
    links = [
        ("pgf.1", "probe.internet.1", False),
        ("dmz.2", "probe.dmz.1", False),
        ("office.2", "probe.office.1", False)
    ]

    policies = {
        "devices" : probes,
        "links" : links
    }

    with open(POLICIES, 'w') as of:
        of.write(json.dumps(policies, indent=2))
