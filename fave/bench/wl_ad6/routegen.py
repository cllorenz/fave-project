#!/usr/bin/env python2

import json

from bench.wl-ad6.inventory import AD6

OFILE="bench/wl-ad6/routes.json"

PGF_ADDR="2001:db8:abc::1"

if __name__ == '__main__':
    hosts, subnets, subhosts = AD6

    # route: (name, table, idx, [fields], [commands])
    routes = [
        ("pgf", 1, 0, ["ipv6_dst=2001:db8:abc:0::0/64"], ["fd=pgf.2"]),
        ("pgf", 1, 0, ["ipv6_dst=2001:db8:abc:1::0/64"], ["fd=pgf.3"]),
        ("pgf", 1, 65535, [], ["fd=pgf.1"]),
        ("dmz", 1, 65535, [], ["fd=dmz.1"]),
        ("wifi", 1, 0, ["ipv6_dst=2001:db8:abc:1::0/64"], ["fd=wifi.2"]),
        ("wifi", 1, 65535, [], ["fd=wifi.1"])
    ]

    # dmz hosts
    for cnt, host in enumerate(hosts):
        name, addr, _services = host
        port = cnt + 2
        routes.extend([
            ("dmz", 1, 0, ["ipv6_dst=%s" % addr], ["fd=dmz.%s" % port]),
            ("%s.dmz" % name, 1, 65535, [], ["fd=%s.dmz.1" % name])
        ])

    # subnets
    for cnt, subnet in enumerate(subnets):
        port = cnt+3
        netident = port+1

        routes.append((
            "pgf",
            1,
            0,
            ["ipv6_dst=2001:db8:abc:%s::0/64" % netident],
            ["fd=pgf.%s" % port]
        ))

        # subnet hosts
        for srv, host in enumerate(subhosts):
            name, _services = host
            ident = srv + 1
            sport = srv + 2
            addr = "2001:db8:abc:%s::%s" % (netident, ident)
            hostnet = "%s.%s" % (name, subnet)

            routes.append((
                subnet, 1, 0,
                ["ipv6_dst=%s" % addr],
                ["fd=%s.%s" % (subnet, sport)]
            ))

            routes.append((hostnet, 1, 0, [], ["fd=%s.%s" % (hostnet, 1)]))

        # subnet clients
        caddr = "2001:db8:abc:%s::100/120" % port
        sport = len(subhosts)+2
        routes.extend([
            (
                subnet, 1, len(subhosts)+1,
                ["ipv6_dst=%s" % caddr],
                ["fd=%s.%s" % (subnet, sport)]
            ),
            ("clients.%s" % subnet, 1, 65535, [], ["fd=clients.%s.1" % subnet])
        ])

        # default rule
        routes.append((subnet, 1, 65535, [], ["fd=%s.1" % subnet]))


    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes, indent=2) + "\n")
