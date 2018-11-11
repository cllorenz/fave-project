#!/usr/bin/env python2

import json

from bench.wl_ad6_inventory import AD6

OFILE="bench/wl-ad6-topology.json"
RULESETS="bench/wl-ad6/rulesets"

PGF_ADDR="2001:db8:abc::1"

if __name__ == '__main__':
    hosts, subnets, subhosts = AD6

    # device: (name, type, no_ports, address)
    devices = [
        ("pgf", "packet_filter", 24, PGF_ADDR, "%s/pgf-ruleset" % RULESETS),
        ("dmz", "switch", 9),
        ("wifi", "switch", 2),
        (
            "clients.wifi",
            "host",
            1,
            "2001:db8:abc:2::100/120",
            "%s/wifi-clients-ruleset" % RULESETS
        )
    ]

    # link: (sname, dname)
    links = [
        ("pgf.26", "dmz.1"),
        ("dmz.1", "pgf.2"),
        ("pgf.27", "wifi.1"),
        ("wifi.1", "pgf.3"),
        ("clients.wifi.2", "wifi.2"),
        ("wifi.2", "clients.wifi.1")
    ]

    # dmz hosts
    for cnt, host in enumerate(hosts):
        name, addr, _services = host
        port = cnt+2

        devices.append((
            "%s.dmz" % name,
            "host",
            1,
            addr,
            "%s/dmz-%s-ruleset" % (RULESETS, name)
        ))
        links.extend([
            ("%s.dmz.2" % name, "dmz.%s" % port),
            ("dmz.%s" % port, "%s.dmz.1" % name)
        ])

    for cnt, subnet in enumerate(subnets):
        port = cnt+4
        netident = port

        # subnet switch
        devices.append((subnet, "switch", len(subhosts)+2))
        links.extend([
            ("pgf.%s" % (port+24), "%s.1" % subnet),
            ("%s.1" % subnet, "pgf.%s" % port)
        ])

        # subnet hosts
        for srv, host in enumerate(subhosts):
            name, _services = host
            ident = srv + 1
            sport = srv + 2
            addr = "2001:db8:abc:%s::%s" % (netident, ident)
            hostnet = "%s.%s" % (name, subnet)
            nethost = "%s-%s" % (subnet, name)

            devices.append((
                hostnet,
                "host",
                1,
                addr,
                "%s/%s-ruleset" % (RULESETS, nethost)
            ))
            links.extend([
                ("%s.%s" % (subnet, sport), "%s.1" % hostnet),
                ("%s.2" % hostnet, "%s.%s" % (subnet, sport))
            ])

        # subnet clients
        devices.append((
            "clients.%s" % subnet,
            "host",
            1,
            "2001:db8:abc:%s::100/120" % netident,
            "%s/%s-clients-ruleset" % (RULESETS, subnet)
        ))
        links.extend([
            ("%s.%s"%(subnet, len(subhosts)+2), "clients.%s.1" % subnet),
            ("clients.%s.2"%subnet, "%s.%s"%(subnet, len(subhosts)+2))
        ])

    devices.append(("source.internet", "generator", ["ipv6_src=0::1/0"]))
    links.append(("source.internet.1", "pgf.1"))

    for cnt, host in enumerate(hosts):
        hname, address, _services = host
        server = "source.%s.dmz" % hname
        devices.append((server, "generator", ["ipv6_src=%s" % address]))
        links.append(("%s.1" % server, "%s.dmz_output_states_in" % hname))

    for cnt, subnet in enumerate(subnets):
        netident = cnt + 4

        for srv, host in enumerate(subhosts):
            ident = srv + 1
            hname, _services = host
            hostnet = "%s.%s" % (hname, subnet)
            server = "source.%s" % hostnet
            addr = "2001:db8:abc:%s::%s" % (netident, ident)

            devices.append((server , "generator", ["ipv6_src=%s" % addr]))
            links.append(("%s.1" % server, "%s_output_states_in" % hostnet))


        caddr = "2001:db8:abc:%s::100/120" % (netident)
        devices.append(
            ("source.clients.%s" % subnet, "generator", ["ipv6_src=%s" % caddr])
        )
        links.append(
            ("source.clients.%s.1" % subnet, "clients.%s_output_states_in" % subnet)
        )


    ad6 = {
        'devices' : devices,
        'links' : links
    }

    with open(OFILE, 'w') as of:
        of.write(json.dumps(ad6, indent=2))
