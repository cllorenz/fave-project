#!/usr/bin/env python2

""" This module generates the IFI workload's topology.
"""

import json

from bench.wl_ifi.inventory import SUBNETS, WITH_IP, WITHOUT_IP

OFILE="bench/wl_ifi/topology.json"

if __name__ == '__main__':
    # device: (name, type, no_ports, acls)

    devices = [
        # central IFI router with 16 ports
        ("ifi", "router", 16, "bench/wl_ifi/acls.txt"),
        # a generator representing the university proxy
        ("source.proxy.uni-potsdam.de", "generator", ["ipv4_src=123.123.0.0/16"])
    ]

    # generators representing the subnets with given IP addresses
    devices.extend([
        (
            "source.%s.ifi" % sub,
            "generator",
            ["vlan=%s" % str(idx+463), "ipv4_src=10.0.%s.0/23" % str((idx+6)*2+1)]
        ) for idx, sub in enumerate(WITH_IP)
    ])

    # generators representing the subnets without given IP addresses
    devices.extend([
        (
            "source.%s.ifi" % sub,
            "generator",
            ["vlan=%s" % str(idx+473)]
        ) for idx, sub in enumerate(WITHOUT_IP)
    ])

    # one switch for every subnet
    # (port: 1 -> connected to the central router,
    #        2 -> input from the generator,
    #        3 -> output to the subnet)
    devices.extend([
        ("%s.ifi" % sub, "switch", 3) for sub in SUBNETS
    ])

    # connect the university proxy to port 1 of the central router
    links = [
        ("source.proxy.uni-potsdam.de.1", "ifi.1")
    ]

    # connect all port 1 of the subnet switches to an input port of the central router
    links.extend([
        ("%s.ifi.1" % sub, "ifi.%s" % str(idx+2)) for idx, sub in enumerate(SUBNETS)
    ])

    # connect the output ports of the central router to port 1 of each subnet switch
    links.extend([
        ("ifi.%s" % str(idx+18), "%s.ifi.1" % sub) for idx, sub in enumerate(SUBNETS)
    ])

    # connect all subnet generators to port 2 of the respective switch
    links.extend([
        ("source.%s.ifi.1" % sub, "%s.ifi.2" % sub) for sub in SUBNETS
    ])

    ifi = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(ifi, indent=2))
