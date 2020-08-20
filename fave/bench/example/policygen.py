#!/usr/bin/env python2

""" This module generates the example workload's policies.
"""

import json

OFILE="bench/example/policies.json"

if __name__ == '__main__':
    probes = [
        # internet
        ("probe.Internet", "probe", "universal", None, None, [
            ".*(p in (dmz.example.com.2,office.example.com.2))$"
        ]),
        # dmz host
        ("probe.dmz.example.com", "probe", "universal", None, None, [
            ".*(p in (fw.example.com.1,office.example.com.2))$"
        ]),
        # office host
        ("probe.office.example.com", "probe", "universal", None, None, [
            ".*(p in (fw.example.com.1,dmz.example.com.2))$"
        ])
    ]


    links = [
        # firewall --> internet
        ("fw.example.com.4", "probe.Internet.1"),
        # dmz switch --> dmz host
        ("dmz.example.com.3", "probe.dmz.example.com.1"),
        # office switch --> office host
        ("office.example.com.3", "probe.office.example.com.1")
    ]

    policies = {
        "probes" : probes,
        "links" : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
