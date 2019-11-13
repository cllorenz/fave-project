#!/usr/bin/env python2

""" This module generates the IFI workload's routes.
"""

import json

from bench.wl_ifi.inventory import SUBNETS, WITH_IP, WITHOUT_IP

IFILE="bench/wl_ifi/inventory.json"
OFILE="bench/wl_ifi/routes.json"

if __name__ == '__main__':
    with open(IFILE, 'r') as inv_file:
        inventory = json.load(inv_file)

    domain_to_ips = inventory["domain_to_ip"]
    domain_to_vlan = inventory["domain_to_vlan"]
    domain_to_ports = inventory["domain_to_ports"]

    routes = [
        # default route to ifi.17 (Internet)
        ("ifi", 1, 65535, [], ["rw=vlan:%s"%(2**12-1), "fd=ifi.18"], []),
        # route to ifi.18 (external)
        ("ifi", 1, 0, ["ipv4_dst=%s" % domain_to_ips["external.ifi"]], ["rw=vlan:48", "fd=ifi.19"], [])
    ]

    # one route per subnet to ports with subnets
    out_port = lambda _ip, op: op
    routes.extend([
        (
            "ifi", 1, idx,
            ["ipv4_dst=%s" % domain_to_ips[sub]],
            [
                "rw=vlan:%s" % domain_to_vlan[sub],
                "fd=ifi.%s" % out_port(*domain_to_ports[sub])
            ],
            []
        ) for idx, sub in enumerate(WITH_IP, start=0) # XXX: starting with 0 is important since a 1 would lead to the default rule being on the first place (-> unpleasant NP behaviour)
    ])

    # one route per subnet sending all traffic to port 3 (internal network)
    routes.append((
        "external.ifi", 1, 0,
        ["ipv4_dst=123.123.48.0/24"],
        ["fd=external.ifi.3"],
        []
    ))
    # routed networks
    routes.extend([
        (
            sub, 1, 0,
            ["ipv4_dst=%s" % domain_to_ips[sub]],
            ["fd=%s.3" % sub],
            []
        ) for sub in WITH_IP
    ])
    # unrouted networks
    routes.extend([
        (
            sub, 1, 0,
            ["ipv4_dst=%s" % "192.168.%s.0/24" % idx],
            ["fd=%s.3" % sub],
            []
        ) for idx, sub in enumerate(WITHOUT_IP, start=0)
    ])

    # one default route per subnet directing towards the router
    routes.append(("external.ifi", 1, 65535, [], ["fd=external.ifi.1"], []))
    routes.extend([
        (
            sub, 1, 65535, [], ["fd=%s.1" % sub], []
        ) for sub in SUBNETS
    ])


    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
