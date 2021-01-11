#!/usr/bin/env python2

import json

from bench.wl_up.inventory import UP

POLICIES="bench/wl_up/policies.json"

if __name__ == '__main__':
    dmz = UP["dmz"]
    subnets = UP["subnets"]
    subhosts = UP["subhosts"]

    # probe: (name, type, quantor, [filter_fields], [test_fields], [test_path])
    probes = [
        ("probe.internet", "probe", "universal", None, None, ["(p in (pgf.uni-potsdam.de.1))"]),
        ("probe.clients.wifi.uni-potsdam.de", "probe", "existential", None, None, [".*(p=pgf.uni-potsdam.de.1);$"]),
        ("probe.pgf.uni-potsdam.de", "probe", "universal", None, None, [".*;(p in (pgf.uni-potsdam.de.2,pgf.uni-potsdam.de.3,pgf.uni-potsdam.de.4,pgf.uni-potsdam.de.5,pgf.uni-potsdam.de.6,pgf.uni-potsdam.de.7,pgf.uni-potsdam.de.8,pgf.uni-potsdam.de.9,pgf.uni-potsdam.de.10,pgf.uni-potsdam.de.11,pgf.uni-potsdam.de.12,pgf.uni-potsdam.de.13,pgf.uni-potsdam.de.14,pgf.uni-potsdam.de.15,pgf.uni-potsdam.de.16,pgf.uni-potsdam.de.17,pgf.uni-potsdam.de.18,pgf.uni-potsdam.de.19,pgf.uni-potsdam.de.20,pgf.uni-potsdam.de.21,pgf.uni-potsdam.de.22,pgf.uni-potsdam.de.23,pgf.uni-potsdam.de.24))"]),
    ]
    links = [
        ("pgf.uni-potsdam.de.1", "probe.internet.1"),
        ("clients.wifi.uni-potsdam.de.input_filter_accept", "probe.clients.wifi.uni-potsdam.de.1"),
        ("pgf.uni-potsdam.de.input_filter_accept", "probe.pgf.uni-potsdam.de.1")
    ]

    # test dmz
    for name, _address, _services in dmz:
        probes.append(
            ("probe.%s" % name, "probe", "existential", None, None, [".*(p=pgf.uni-potsdam.de.1);$"])
        )
        links.append(
            ("%s.input_filter_accept" % name, "probe.%s.1" % name)
        )


    # test subnets
    for subnet in subnets:
        for subhost, _services in subhosts:
            hostnet = "%s.%s" % (subhost, subnet)

            probes.append((
                "probe.%s" % hostnet,
                "probe",
                "existential",
                None,
                None,
                [".*(p=pgf.uni-potsdam.de.1);$"]
            ))

            links.append(
                ("%s.input_filter_accept" % hostnet, "probe.%s.1" % hostnet)
            )


        probes.append((
            "probe.clients.%s" % subnet,
            "probe",
            "existential",
            ["tcp_dst=22"],
            None,
            [".*(p=pgf.uni-potsdam.de.1);$"]
        ))

        links.append(
            ("clients.%s.input_filter_accept" % subnet, "probe.clients.%s.1" % subnet)
        )


    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(POLICIES, 'w') as of:
        of.write(json.dumps(policies, indent=2))
