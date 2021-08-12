#!/usr/bin/env python2

import json
TOPOLOGY="bench/wl_example/topology.json"
SOURCES="bench/wl_example/sources.json"
RULESETS="bench/wl_example/rulesets"

if __name__ == '__main__':
    # device: (name, type, no_ports, address, ruleset)
    devices = [
        ("pgf", "packet_filter", 3, "2001:db8::1", "%s/pgf-ruleset" % RULESETS),
        ("dmz", "switch", 2, None),
        ("office", "switch", 2, None)
    ]

    # link: (sname, dname)
    links = [
        ("pgf.2", "dmz.1", False),
        ("dmz.1", "pgf.2", False),
        ("pgf.3", "office.1", False),
        ("office.1", "pgf.3", False)
    ]


    # source nodes
    sources = [
        ("source.internet", "generator", ["ipv6_src=0::0/0"]),
        ("source.dmz", "generator", ["ipv6_src=2001:db8::100/120"]),
        ("source.office", "generator", ["ipv6_src=2001:db8::200/120"])
    ]

    # source links
    source_links = [
        ("source.internet.1", "pgf.1", True),
        ("source.dmz.1", "dmz.2", True),
        ("source.office.1", "office.2", True)
    ]


    topology = {
        'devices' : devices,
        'links' : links
    }

    sources = {
        'devices' : sources,
        'links' : source_links
    }

    json.dump(topology, open(TOPOLOGY, 'w'), indent=2)
    json.dump(sources, open(SOURCES, 'w'), indent=2)
