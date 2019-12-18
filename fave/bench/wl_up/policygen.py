#!/usr/bin/env python2

import json

from bench.wl_up.inventory import UP

POLICIES="bench/wl_up/policies.json"

if __name__ == '__main__':
    hosts = UP["dmz"]
    subnets = UP["subnets"]
    subhosts = UP["subhosts"]

    # probe: (name, type, quantor, [filter_fields], [test_fields], [test_path])
    probes = [
        ("probe.internet", "probe", "universal", None, None, ["(p in (pgf.uni-potsdam.de.25))"]),
        ("probe.clients.wifi.uni-potsdam.de", "probe", "existential", None, None, [".*(p=pgf.uni-potsdam.de.1);$"])
    ]
    links = [
        ("pgf.uni-potsdam.de.25", "probe.internet.1"),
        ("clients.wifi.uni-potsdam.de_input_states_accept", "probe.clients.wifi.uni-potsdam.de.1"),
        ("clients.wifi.uni-potsdam.de_input_rules_accept", "probe.clients.wifi.uni-potsdam.de.1")
    ]

    # test dmz
    for name, _address, _services in hosts:
        probes.append(
            ("probe.%s.uni-potsdam.de" % name, "probe", "existential", ["tcp_dst=22"], None, [".*(p=pgf.uni-potsdam.de.1);$"])
        )
        links.extend([
            ("%s.uni-potsdam.de_input_states_accept" % name, "probe.%s.uni-potsdam.de.1" % name),
            ("%s.uni-potsdam.de_input_rules_accept" % name, "probe.%s.uni-potsdam.de.1" % name)
        ])

    # test subnets
    for subnet in subnets:
        for subhost, _services in subhosts:
            hostnet = "%s.%s" % (subhost, subnet)

            probes.append((
                "probe.%s" % hostnet,
                "probe",
                "existential",
                ["tcp_dst=22"],
                None,
                [".*(p=pgf.uni-potsdam.de.1);$"]
            ))

            links.extend([
                ("%s_input_states_accept" % hostnet, "probe.%s.1" % hostnet),
                ("%s_input_rules_accept" % hostnet, "probe.%s.1" % hostnet)
            ])

        probes.append((
            "probe.clients.%s" % subnet,
            "probe",
            "existential",
            ["tcp_dst=22"],
            None,
            [".*(p=pgf.uni-potsdam.de.1);$"]
        ))

        links.extend([
            ("clients.%s_input_states_accept" % subnet, "probe.clients.%s.1" % subnet),
            ("clients.%s_input_rules_accept" % subnet, "probe.clients.%s.1" % subnet)
        ])


    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(POLICIES, 'w') as of:
        of.write(json.dumps(policies, indent=2))
