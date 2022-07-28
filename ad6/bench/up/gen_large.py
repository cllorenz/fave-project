#!/usr/bin/env python3

import lxml.etree as et

from bench.up.inventory import UP
from src.xml.genutils import GenUtils
from src.xml.xmlutils import XMLUtils

RULESETS = 'bench/up'

def _gen_node(name, addr, _ports):
    node = GenUtils.node(name)

    node.append(GenUtils.nodeFirewall(name))

    if addr:
        node.append(GenUtils.address(addr))

    return node


def _gen_if(node_name, if_no):
    if_name = "%s_%d" % (node_name, if_no)
    return if_name, GenUtils.interface(str(if_no), if_name)


def _connect_interfaces(src, dst):
    conn = GenUtils.connections()
    conn.append(GenUtils.connection(dst))

    src.append(conn)


def _set_route(if_, prefix, negated=False):
    rts = if_.find('routes')
    if not rts:
        rts = GenUtils.routes()
        if_.append(rts)

    rts.append(GenUtils.route(prefix, flag=not negated))


if __name__ == '__main__':
    devices = {}
    interfaces = {}

    internet_name = 'internet'
    internet = _gen_node(internet_name, "0::0/0", [])
    devices[internet_name] = internet
    internet_if_name, internet_if = _gen_if(internet_name, 1)
    internet.append(internet_if)
    interfaces[internet_if_name] = internet_if
    _set_route(internet_if, "0::0/0")

    pgf_name = UP['pgf'][0][0]
    pgf = _gen_node(*UP['pgf'][0])
    devices[pgf_name] = pgf

    wifi = UP['wifi'][0]
    wifi_clients_name = wifi[0]
    wifi_clients = _gen_node(*wifi)
    devices[wifi_clients_name] = wifi_clients
    wifi_clients_if_name, wifi_clients_if = _gen_if(wifi_clients_name, 1)
    interfaces[wifi_clients_if_name] = wifi_clients_if
    wifi_clients.append(wifi_clients_if)

    dmz_name = 'dmz.uni-potsdam.de'
    dmz = _gen_node(dmz_name, None, [])
    devices['dmz.uni-potsdam.de'] = dmz

    for i_ in range(1, 24+1):
        if_name, if_ = _gen_if(pgf_name, i_)
        pgf.append(if_)
        interfaces[if_name] = if_

    for i_ in range(1, 9+1):
        if_name, if_ = _gen_if(dmz_name, i_)
        dmz.append(if_)
        interfaces[if_name] = if_

    links = [
        ("internet_1", "pgf.uni-potsdam.de_1"),
        ("pgf.uni-potsdam.de_1", "internet_1"),
        ("pgf.uni-potsdam.de_2", "dmz.uni-potsdam.de_1"),
        ("dmz.uni-potsdam.de_1", "pgf.uni-potsdam.de_2"),
        ("pgf.uni-potsdam.de_3", "clients.wifi.uni-potsdam.de_1"),
        ("clients.wifi.uni-potsdam.de_1", "pgf.uni-potsdam.de_3")
    ]

    for src, dst in links:
        src = interfaces[src]
        _connect_interfaces(src, dst)


    routes = [
        # pgf -> dmz
        ("2001:db8:abc:1::0/64", "pgf.uni-potsdam.de_2"),
        # pgf -> wifi
        (wifi[1], "pgf.uni-potsdam.de_3")
    ]

    for prefix, if_ in routes:
        if_ = interfaces[if_]
        _set_route(if_, prefix)


    # dmz
    dmz_hosts = UP['dmz']
    import sys
    for cnt, host in enumerate(dmz_hosts, start=2):
        host_name, addr, ports = host
        port = cnt

        host = _gen_node(*host)
        devices[host_name] = host

        host_if_name, host_if = _gen_if(host_name, 1)
        host.append(host_if)
        interfaces[host_if_name] = host_if

        dmz_if_name = "%s_%d" % (dmz_name, port)

        _connect_interfaces(host_if, dmz_if_name)
        _connect_interfaces(interfaces[dmz_if_name], host_if_name)

        # dmz -> host
        _set_route(interfaces[dmz_if_name], addr)

        # not host -> dmz
        _set_route(host_if, addr, negated=True)


    default_routes = [
        # not uni-potsdam.de routing domain -> internet
        ("2001:db8:abc::0/48", "pgf.uni-potsdam.de_1"),
        # not dmz -> pgf
        ("2001:db8:abc:1::0/64", "dmz.uni-potsdam.de_1"),
        # not wifi -> pgf
        (wifi[1], "clients.wifi.uni-potsdam.de_1")
    ]

    for prefix, if_ in default_routes:
        _set_route(interfaces[if_], prefix, negated=True)


    subnets = UP['subnets']
    subhosts = UP['subhosts']

    for cnt, subnet_name in enumerate(subnets, start=4):
        port = cnt
        netident = cnt

        # switch
        subnet = _gen_node(subnet_name, None, [])
        devices[subnet_name] = subnet

        # switch interfaces
        for if_no in range(1, len(subhosts)+3):
            if_name, if_ = _gen_if(subnet_name, if_no)
            interfaces[if_name] = if_
            subnet.append(if_)

        # pgf -> subnet
        _connect_interfaces(
            interfaces["%s_%d" % (pgf_name, netident)], "%s_1" % subnet_name
        )
        _connect_interfaces(
            interfaces["%s_1" % subnet_name], "%s_%d" % (pgf_name, netident)
        )
        _set_route(
            interfaces["%s_%d" % (pgf_name, netident)],
            "2001:db8:abc:%x::0/64" % netident
        )

        # clients
        subnet_clients_name = "clients.%s" % subnet_name
        subnet_clients = _gen_node(
            subnet_clients_name, "2001:db8:abc:%x::100/120" % netident, []
        )
        devices[subnet_clients_name] = subnet_clients
        subnet_clients_if_name, subnet_clients_if = _gen_if(subnet_clients_name, 1)
        subnet_clients.append(subnet_clients_if)
        interfaces[subnet_clients_if_name] = subnet_clients_if
        _set_route(
            interfaces["%s_%d" % (subnet_name, len(subhosts)+2)],
            "2001:db8:abc:%x::100/120" % netident
        )
        _set_route(
            subnet_clients_if,
            "2001:db8:abc:%x::100/120" % netident,
            negated=True
        )

        subnet_if_name = "%s_%d" % (subnet_name, len(subhosts)+2)
        _connect_interfaces(subnet_clients_if, subnet_if_name)
        _connect_interfaces(
            interfaces[subnet_if_name],
            "%s_1" % subnet_clients_name
        )

        # subhosts
        for cnt, subhost in enumerate(subhosts, start=2):
            subhost_if_no = cnt
            ident = cnt-1
            subhost_name, ports = subhost

            subhost_name = "%s_%s" % (subhost_name, subnet_name)

            subhost = _gen_node(
                subhost_name, "2001:db8:abc:%x::%x" % (netident, ident), ports
            )
            devices[subhost_name] = subhost
            subhost_if_name, subhost_if = _gen_if(subhost_name, 1)
            subhost.append(subhost_if)
            interfaces[subhost_if_name] = subhost_if
            _set_route(
                subhost_if,
                "2001:db8:abc:%x::%x" % (netident, ident),
                negated=True
            )

            subnet_if_name = "%s_%d" % (subnet_name, subhost_if_no)
            _set_route(
                interfaces[subnet_if_name],
                "2001:db8:abc:%x::%x" % (netident, ident)
            )
            _connect_interfaces(subhost_if, subnet_if_name)
            _connect_interfaces(
                interfaces[subnet_if_name], "%s_1" % subhost_name
            )

        # default routes
        _set_route(
            interfaces["%s_1" % subnet_name],
            "2001:db8:abc:%x::0/64" % netident,
            negated=True
        )

    networks = GenUtils.networks()
    network = GenUtils.network('')
    network.extend(devices.values())

    networks.append(network)

    config = GenUtils.config()
    config.append(networks)

    ctree = et.ElementTree(config)

    with open('bench/up/large.xml', 'w') as ofile:
        ofile.write(et.tostring(ctree, pretty_print=True).decode('UTF-8'))
