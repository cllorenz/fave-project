#!/usr/bin/env python2

import json

from bench.wl_up.inventory import UP

OFILE="bench/wl_up/routes.json"

if __name__ == '__main__':
    dmz = UP["dmz"]
    subnets = UP["subnets"]
    subhosts = UP["subhosts"]

    # route: (name, table, idx, [fields], [commands])
    routes = [
        # pgf -> dmz
        ("pgf.uni-potsdam.de", 1, 0, ["ipv6_dst=2001:db8:abc:1::0/64"], ["fd=pgf.uni-potsdam.de.2"], []),
        # pgf -> wifi
        ("pgf.uni-potsdam.de", 1, 1, ["ipv6_dst=2001:db8:abc:2::0/64"], ["fd=pgf.uni-potsdam.de.3"], []),
        # pgf -> internet
        ("pgf.uni-potsdam.de", 1, 65535, [], ["fd=pgf.uni-potsdam.de.1"], []),
        # dmz -> pgf
        ("dmz.uni-potsdam.de", 1, 65535, [], ["fd=dmz.uni-potsdam.de.1"], ["dmz.uni-potsdam.de.%s" % p for p in range(2, 9+1)]),
        # wifi -> wifi
        ("wifi.uni-potsdam.de", 1, 0, ["ipv6_dst=2001:db8:abc:2::100/120"], ["fd=wifi.uni-potsdam.de.2"], ["wifi.uni-potsdam.de.1", "wifi.uni-potsdam.de.3"]),
        # wifi -> pgf
        ("wifi.uni-potsdam.de", 1, 65535, [], ["fd=wifi.uni-potsdam.de.1"], ["wifi.uni-potsdam.de.3"]),
        # wifi -> wifi
        ("clients.wifi.uni-potsdam.de", 1, 65535, [], ["fd=clients.wifi.uni-potsdam.de.1"], [])
    ]

    # dmz hosts
    for cnt, host in enumerate(dmz):
        name, addr, _services = host
        port = cnt+2
        routes.extend([
            # dmz -> host
            ("dmz.uni-potsdam.de", 1, cnt, ["ipv6_dst=%s" % addr], ["fd=dmz.uni-potsdam.de.%s" % port], []),
            # host -> dmz
            (name, 1, 65535, [], ["fd=%s.1" % name], [])
        ])


    # subnets
    for cnt, subnet in enumerate(subnets):
        port = cnt+4
        netident = cnt+4

        routes.append((
            "pgf.uni-potsdam.de",
            1,
            cnt+2,
            ["ipv6_dst=2001:db8:abc:%s::0/64" % netident],
            ["fd=pgf.uni-potsdam.de.%s" % port],
            []
        ))

        # subnet hosts
        for srv, host in enumerate(subhosts):
            name, _services = host
            ident = srv + 1
            sport = srv + 2
            addr = "2001:db8:abc:%s::%s" % (netident, ident)
            hostnet = "%s.%s" % (name, subnet)

            routes.append((
                subnet, 1, srv,
                ["ipv6_dst=%s" % addr],
                ["fd=%s.%s" % (subnet, sport)],
                []
            ))

            routes.append((hostnet, 1, 65535, [], ["fd=%s.1" % hostnet], []))


        # subnet clients
        caddr = "2001:db8:abc:%s::100/120" % netident
        sport = len(subhosts)+2
        routes.extend([
            (
                subnet, 1, len(subhosts)+1,
                ["ipv6_dst=%s" % caddr],
                ["fd=%s.%s" % (subnet, sport)], []
            ),
            ("clients.%s" % subnet, 1, 65535, [], ["fd=clients.%s.1" % subnet], [])
        ])

        # default rule
        routes.append((subnet, 1, 65535, [], ["fd=%s.1" % subnet], []))

    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
