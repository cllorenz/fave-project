#!/usr/bin/env python2

import json

OFILE="bench/wl-ifi/topology.json"

if __name__ == '__main__':
    # device: (name, type, no_ports, acls)
    devices = [
        ("ifi", "router", 12, "bench/wl-ifi/acls.txt"),
        ("source.internet", "generator", ["ipv4_src=0.0.0.0/0"]),
        ("source.ifi", "generator", ["vlan=463", "ipv4_src=10.0.13.0/23"])
    ]

    links = [
        ("source.internet.1", "ifi.1"),
        ("source.ifi.1", "ifi.2")
    ]

    ifi = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(ifi, indent=2))
