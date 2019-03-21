#!/usr/bin/env python2

""" This module generates the IFI workload's topology.
"""

import json

from bench.wl_ifi.inventory import SUBNETS, WITH_IP, WITHOUT_IP

OFILE="bench/wl_ifi/topology.json"

if __name__ == '__main__':
    # device: (name, type, no_ports, acls)
    devices = [
        ("ifi", "router", 16, "bench/wl_ifi/acls.txt"),
        ("source.proxy.uni-potsdam.de", "generator", ["ipv4_src=123.123.0.0/16"])
    ]

    devices.extend([
        (
            "source.%s.ifi" % sub,
            "generator",
            ["vlan=%s" % str(idx+463), "ipv4_src=10.0.%s.0/23" % str((idx+6)*2+1)]
        ) for idx, sub in enumerate(WITH_IP)
    ])

    devices.extend([
        (
            "source.%s.ifi" % sub,
            "generator",
            ["vlan=%s" % str(idx+473)]
        ) for idx, sub in enumerate(WITHOUT_IP)
    ])

    devices.extend([
        ("%s.ifi" % sub, "switch", 3) for sub in SUBNETS
    ])

    links = [
        ("source.proxy.uni-potsdam.de.1", "ifi.1")
    ]

    links.extend([
        ("%s.ifi.1" % sub, "ifi.%s" % str(idx+2)) for idx, sub in enumerate(SUBNETS)
    ])

    links.extend([
        ("ifi.%s" % str(idx+18), "%s.ifi.1" % sub) for idx, sub in enumerate(SUBNETS)
    ])

    links.extend([
        ("source.%s.ifi.1" % sub, "%s.ifi.2" % sub) for sub in SUBNETS
    ])

    ifi = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(ifi, indent=2))
