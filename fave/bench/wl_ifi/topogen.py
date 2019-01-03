#!/usr/bin/env python2

import json

OFILE="bench/wl_ifi/topology.json"

if __name__ == '__main__':
    # device: (name, type, no_ports, acls)
    devices = [
        ("ifi", "router", 16, "bench/wl_ifi/acls.txt"),
        ("source.up", "generator", ["ipv4_src=123.123.0.0/16"]),
        ("source.internal.ifi", "generator", ["vlan=463", "ipv4_src=10.0.13.0/23"]),
        ("source.admin.ifi", "generator", ["vlan=464", "ipv4_src=10.0.15.0/23"]),
        ("source.office.ifi", "generator", ["vlan=465", "ipv4_src=10.0.17.0/23"]),
        ("source.staff-1.ifi", "generator", ["vlan=466", "ipv4_src=10.0.19.0/23"]),
        ("source.staff-2.ifi", "generator", ["vlan=467", "ipv4_src=10.0.21.0/23"]),
        ("source.pool.ifi", "generator", ["vlan=468", "ipv4_src=10.0.13.0/23"]),
        ("source.lab.ifi", "generator", ["vlan=469", "ipv4_src=10.0.25.0/23"]),
        ("source.hpc-mgt.ifi", "generator", ["vlan=470", "ipv4_src=10.0.27.0/23"]),
        ("source.hpc-ic.ifi", "generator", ["vlan=471", "ipv4_src=10.0.29.0/23"]),
        ("source.slb.ifi", "generator", ["vlan=472", "ipv4_src=10.0.31.0/23"]),
        ("source.mgt.ifi", "generator", ["vlan=473"]),
        ("source.san.ifi", "generator", ["vlan=474"]),
        ("source.vmo.ifi", "generator", ["vlan=475"]),
        ("source.prt.ifi", "generator", ["vlan=476"]),
        ("source.cam.ifi", "generator", ["vlan=477"])
    ]

    links = [
        ("source.up.1", "ifi.1"),
        ("source.internal.ifi.1", "ifi.2"),
        ("source.admin.ifi.1", "ifi.3"),
        ("source.office.ifi.1", "ifi.4"),
        ("source.staff-1.ifi.1", "ifi.5"),
        ("source.staff-2.ifi.1", "ifi.6"),
        ("source.pool.ifi.1", "ifi.7"),
        ("source.lab.ifi.1", "ifi.8"),
        ("source.hpc-mgt.ifi.1", "ifi.9"),
        ("source.hpc-ic.ifi.1", "ifi.10"),
        ("source.slb.ifi.1", "ifi.11"),
        ("source.mgt.ifi.1", "ifi.12"),
        ("source.san.ifi.1", "ifi.13"),
        ("source.vmo.ifi.1", "ifi.14"),
        ("source.prt.ifi.1", "ifi.15"),
        ("source.cam.ifi.1", "ifi.16")
    ]

    ifi = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(ifi, indent=2))
