#!/usr/bin/env python2

import json

from bench.wl_up.inventory import AD6

POLICIES="bench/wl_up/policies.json"

if __name__ == '__main__':
    hosts, subnets, subhosts = AD6

    # probe: (name, type, quantor, [filter_fields], [test_fields], [test_path])
    probes = [
        ("probe.internet", "probe", "universal", None, None, ["(p in (pgf.25))"]),
        ("probe.clients.wifi", "probe", "existential", None, None, [".*(p=pgf.1);$"])
    ]
    links = [
        ("pgf.25", "probe.internet.1"),
        ("clients.wifi_input_states_accept", "probe.clients.wifi.1"),
        ("clients.wifi_input_rules_accept", "probe.clients.wifi.1")
    ]

    # test dmz
    for name, _address, _services in hosts:
        probes.append(
            ("probe.%s.dmz" % name, "probe", "existential", ["tcp_dst=22"], None, [".*(p=pgf.1);$"])
        )
        links.extend([
            ("%s.dmz_input_states_accept" % name, "probe.%s.dmz.1" % name),
            ("%s.dmz_input_rules_accept" % name, "probe.%s.dmz.1" % name)
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
                [".*(p=pgf.1);$"]
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
            [".*(p=pgf.1);$"]
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
