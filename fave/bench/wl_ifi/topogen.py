#!/usr/bin/env python2

""" This module generates the IFI workload's topology.
"""

import json

from bench.wl_ifi.inventory import SUBNETS, WITH_IP, WITHOUT_IP

TOPOLOGY="bench/wl_ifi/topology.json"
SOURCES="bench/wl_ifi/sources.json"
INVENTORY="bench/wl_ifi/inventory.json"

if __name__ == '__main__':
    with open(INVENTORY, "r") as ifile:
        inventory = json.load(ifile)
        domain_to_vlan = inventory['domain_to_vlan']
        domain_to_ip = inventory['domain_to_ip']
        domain_to_ports = inventory['domain_to_ports']

    # device: (name, type, no_ports, acls)
    devices = [
        # central IFI router with 17 ports
        ("ifi", "router", 17, "bench/wl_ifi/acls.txt"),
        # a switch and generator representing the subnet for external services
        ("external.ifi", "switch", 3, None)
    ]

    sources = [
        # a generator representing the Internet
        ("source.Internet", "generator", ["ipv4_src=%s" % domain_to_ip["Internet"]]),
        ("source.external.ifi", "generator", [
            "ipv4_src=%s" % domain_to_ip["external.ifi"],
            "vlan=%s" % domain_to_vlan["external.ifi"]
        ])
    ]

    # generators representing the subnets with given IP addresses
    sources.extend([
        (
            "source.%s" % sub,
            "generator",
            [
                "vlan=%s" % domain_to_vlan[sub],
                "ipv4_src=%s" % domain_to_ip[sub]
            ]
        ) for sub in WITH_IP
    ])

    sources.extend([
        (
            "source.%s" % sub,
            "generator",
            ["vlan=%s" % domain_to_vlan[sub]]
        ) for sub in WITHOUT_IP
    ])

    # one switch for every subnet
    # (port: 1 -> connected to the central router,
    #        2 -> input from the generator,
    #        3 -> output to the subnet)
    devices.extend([
        (sub, "switch", 3, None) for sub in SUBNETS
    ])

    # connect the university proxy to port 1 of the central router
    # connect the Internet to port 1 of the central router
    links = [
        ("external.ifi.1", "ifi.2", False),
        ("ifi.2", "external.ifi.1", False)
    ]
    source_links = [
        ("source.Internet.1", "ifi.1", True),
        ("source.external.ifi.1", "external.ifi.2", True)
    ]

    # connect all port 1 of the subnet switches to an input port of the central router
    in_port = lambda ip, _op: ip
    links.extend([
        ("%s.1" % sub, "ifi.%s" % in_port(*domain_to_ports[sub]), False) for sub in SUBNETS
    ])

    # connect the output ports of the central router to port 1 of each subnet switch
    out_port = lambda _ip, op: op
    links.extend([
        ("ifi.%s" % out_port(*domain_to_ports[sub]), "%s.1" % sub, False) for idx, sub in enumerate(SUBNETS, start=3)
    ])

    # connect all subnet generators to port 2 of the respective switch
    source_links.extend([
        ("source.%s.1" % sub, "%s.2" % sub, True) for sub in SUBNETS
    ])

    with open(TOPOLOGY, 'w') as of:
        of.write(json.dumps({'devices' : devices, 'links' : links}, indent=2))

    with open(SOURCES, 'w') as of:
        of.write(json.dumps({'devices' : sources, 'links' : source_links}, indent=2))
