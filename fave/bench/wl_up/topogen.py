#!/usr/bin/env python2

import json

from bench.wl_up.inventory import UP

TOPOLOGY="bench/wl_up/topology.json"
SOURCES="bench/wl_up/sources.json"
RULESETS="bench/wl_up/rulesets"

if __name__ == '__main__':
    get_domain = lambda domain, _addr, _services: domain
    get_addr = lambda _domain, addr, _services: addr
    get_services = lambda _domain, _addr, services: services

    pgf = UP["pgf"][0]
    wifi = UP["wifi"][0]

    # device: (name, type, no_ports, address, ruleset)
    devices = [
        (get_domain(*pgf), "packet_filter", 24, get_addr(*pgf), "%s/pgf.uni-potsdam.de-ruleset" % RULESETS),
#        (get_domain(*pgf), "packet_filter", 24, get_addr(*pgf), "%s/simple-ruleset" % RULESETS),
        ("dmz.uni-potsdam.de", "switch", 9),
        ("wifi.uni-potsdam.de", "switch", 3),
        (
            "clients.wifi.uni-potsdam.de", #get_domain(*wifi),
            "host",
            1,
            "2001:db8:abc:2::100/120", #get_addr(*wifi),
            "%s/wifi.uni-potsdam.de-clients-ruleset" % RULESETS
        )
    ]

    # link: (sname, dname)
    links = [
        ("pgf.uni-potsdam.de.26", "dmz.uni-potsdam.de.1"),
        ("dmz.uni-potsdam.de.1", "pgf.uni-potsdam.de.2"),
        ("pgf.uni-potsdam.de.27", "wifi.uni-potsdam.de.1"),
        ("wifi.uni-potsdam.de.1", "pgf.uni-potsdam.de.3"),
        ("wifi.uni-potsdam.de.2", "clients.wifi.uni-potsdam.de.1"),
        ("clients.wifi.uni-potsdam.de.2", "wifi.uni-potsdam.de.3")
    ]


    # source nodes
    sources = [
        ("source.internet", "generator", ["ipv6_src=0::0/0"]),
        ("source.clients.wifi.uni-potsdam.de", "generator", ["ipv6_src=2001:db8:abc:2::100/120"]),
        ("source.pgf.uni-potsdam.de", "generator", ["ipv6_src=%s" % get_addr(*pgf)])
    ]

    # source links
    source_links = [
        ("source.internet.1", "pgf.uni-potsdam.de.1"),
        ("source.clients.wifi.uni-potsdam.de.1", "clients.wifi.uni-potsdam.de_output_states_in"),
        ("source.pgf.uni-potsdam.de.1", "pgf.uni-potsdam.de_output_states_in")
    ]



    # dmz hosts
    dmz = UP["dmz"]

    for cnt, host in enumerate(dmz, start=2):
        name = get_domain(*host)
        addr = get_addr(*host)
        port = cnt

        devices.append((
            name,
            "host",
            1,
            addr,
            "%s/dmz-%s-ruleset" % (RULESETS, name)
        ))
        links.extend([
            ("%s.2" % name, "dmz.uni-potsdam.de.%s" % port),
            ("dmz.uni-potsdam.de.%s" % port, "%s.1" % name)
        ])

    subnets = UP["subnets"]
    subhosts = UP["subhosts"]

    for cnt, subnet in enumerate(subnets, start=4):
        port = cnt
        netident = cnt

        # subnet switch
        devices.append((subnet, "switch", len(subhosts)+2))
        links.extend([
            ("pgf.uni-potsdam.de.%s" % (port+24), "%s.1" % subnet),
            ("%s.1" % subnet, "pgf.uni-potsdam.de.%s" % port)
        ])

        # subnet hosts
        for srv, host in enumerate(subhosts, start=1):
            name, _services = host
            ident = srv
            sport = srv + 1
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


    for host in dmz:
        hname = get_domain(*host)
        address = get_addr(*host)
        server = "source.%s" % hname
        sources.append((server, "generator", ["ipv6_src=%s" % address]))
        source_links.append(("%s.1" % server, "%s_output_states_in" % hname))

    for cnt, subnet in enumerate(subnets, start=4):
        netident = cnt

        for srv, host in enumerate(subhosts):
            ident = srv + 1
            hname, _services = host
            hostnet = "%s.%s" % (hname, subnet)
            server = "source.%s" % hostnet
            addr = "2001:db8:abc:%s::%s" % (netident, ident)

            sources.append((server , "generator", ["ipv6_src=%s" % addr]))
            source_links.append(("%s.1" % server, "%s_output_states_in" % hostnet))

            break


        caddr = "2001:db8:abc:%s::100/120" % (netident)
        sources.append(
            ("source.clients.%s" % subnet, "generator", ["ipv6_src=%s" % caddr])
        )
        source_links.append(
            ("source.clients.%s.1" % subnet, "clients.%s_output_states_in" % subnet)
        )

        break


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
