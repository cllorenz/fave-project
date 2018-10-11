#!/usr/bin/env python2

""" This module benchmarks FaVe with the AD6 workload.
"""

import os
import sys
import logging
import time

import netplumber.dump_np as dumper
import test.check_flows as checker
#import netplumber.print_np as printer

from topology import topology as topo
from ip6np import ip6np as ip6tables
from openflow import switch


LOGGER = logging.getLogger("ad6")
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.DEBUG)

TMPDIR = "/tmp/np"
os.system("mkdir -p %s" % TMPDIR)

LOGGER.info("deleting old logs and measurements...")
os.system("rm -f %s/*.log" % TMPDIR)
LOGGER.info("deleted old logs and measurements.")

logging.basicConfig(
    format='%(asctime)s [%(name)s.%(levelname)s] - %(message)s',
    level=logging.INFO,
    filename="%s/fave.log" % TMPDIR,
    filemode='w'
)

LOG_HANDLER = logging.FileHandler("%s/fave.log" % TMPDIR)
#    LOG_HANDLER.setFormatter(
#        logging.Formatter('%(asctime)s %(levelname)s %(message)s')
#    )

PF_LOGGER = logging.getLogger("pf")
PF_LOGGER.addHandler(LOG_HANDLER)
PF_LOGGER.setLevel(logging.INFO)

PFR_LOGGER = logging.getLogger("pfr")
PFR_LOGGER.addHandler(LOG_HANDLER)
PFR_LOGGER.setLevel(logging.INFO)

SUB_LOGGER = logging.getLogger("sub")
SUB_LOGGER.addHandler(LOG_HANDLER)
SUB_LOGGER.setLevel(logging.INFO)

LINK_LOGGER = logging.getLogger("link")
LINK_LOGGER.addHandler(LOG_HANDLER)
LINK_LOGGER.setLevel(logging.INFO)

SW_LOGGER = logging.getLogger("sw")
SW_LOGGER.addHandler(LOG_HANDLER)
SW_LOGGER.setLevel(logging.INFO)

SRC_LOGGER = logging.getLogger("src")
SRC_LOGGER.addHandler(LOG_HANDLER)
SRC_LOGGER.setLevel(logging.INFO)

PROBE_LOGGER = logging.getLogger("probe")
PROBE_LOGGER.addHandler(LOG_HANDLER)
PROBE_LOGGER.setLevel(logging.INFO)


def measure(function, logger=LOGGER):
    """ Measures the duration of a function call in milliseconds.

    Keyword arguments:
    function -- a function to be called
    logger -- a logger for the measurement result (default: stdout)
    """

    t_start = time.time()
    function()
    t_end = time.time()

    logger.info("%fms", (t_end-t_start)*1000.0)


def _add_packet_filter(name, address, ports):
    measure(
        lambda: topo.main([
            "-a",
            "-t", "packet_filter",
            "-n", name,
            "-i", address,
            "-p", str(ports)
        ]),
        PF_LOGGER
    )


def _add_switch(name, ports):
    measure(
        lambda: topo.main(["-a", "-t", "switch", "-n", name, "-p", str(ports)]),
        SUB_LOGGER
    )


def _link_ports(ports):
    measure(
        lambda: topo.main(["-a", "-l", ','.join(["%s:%s" % (s, d) for s, d in ports])]),
        LINK_LOGGER
    )


def _add_ruleset(name, ports, address, ruleset):
    measure(
        lambda: ip6tables.main(["-n", name, "-p", ports, "-i", address, "-f", ruleset]),
        PFR_LOGGER
    )


def _add_switch_rule(name, table=None, idx=None, fields=None, commands=None):
    opts = []
    if table:
        opts.extend(["-t", str(table)])
    if idx:
        opts.extend(["-i", str(idx)])
    if fields:
        opts.extend(["-f", ';'.join(fields)])
    if commands:
        opts.extend(["-c", ','.join(commands)])

    measure(
        lambda: switch.main(["-a", "-n", name] + opts),
        SW_LOGGER
    )


def _add_probe(name, quantor, filter_fields=None, test_fields=None, test_path=None):
    opts = []
    if filter_fields:
        opts.extend(["-F", ';'.join(filter_fields)])
    if test_fields:
        opts.extend(["-T", ';'.join(test_fields)])
    if test_path:
        opts.extend(["-P", ';'.join(test_path)])

    measure(
        lambda: topo.main(["-a", "-t", "probe", "-n", name, "-q", quantor] + opts),
        PROBE_LOGGER
    )


def _add_generator(name, fields=None):
    opts = []
    if fields:
        opts.extend(["-f", ';'.join(fields)])

    measure(
        lambda: topo.main(["-a", "-t", "generator", "-n", name] + opts),
        SRC_LOGGER
    )


def _create_subnet_switches(cnt, subnets, subhosts):
    for net in subnets:
        LOGGER.info("  creating subnet %s...", net)

        # create switch for subnet
        _add_switch(net, len(subhosts)+2)

        # link switch to firewall
        _link_ports([
            ("pgf.%s"%(cnt+24), "%s.1"%net),
            ("%s.1"%net, "pgf.%s"%cnt)
        ])
        LOGGER.info("  created subnet %s.", net)
        cnt += 1


def _set_dmz_switch_rules(cnt, hosts):
    for host in hosts:
        addr = host[1]

        # forwarding rule to host
        LOGGER.debug("\tset rule: ipv6_dst=%s -> fd=dmz.1", addr)
        _add_switch_rule("dmz", 1, 1, ["ipv6_dst=%s" % addr], ["fd=dmz.%s" % cnt])

        cnt += 1


def _set_subnet_switch_rules(cnt, subnets, subhosts):
    for net in subnets:
        for srv in range(1, len(subhosts)+1):
            ident = srv
            port = srv+1

            addr = "2001:db8:abc:%s::%s" % (cnt, ident)

            # forwarding rule to server
            LOGGER.debug("set rule: ipv6_dst=%s -> fd=%s.%s", addr, net, port)
            _add_switch_rule(
                net, 1, 1,
                ["ipv6_dst=%s" % addr],
                ["fd=%s.%s" % (net, port)]
            )

        # forwarding rule to clients
        addr = "2001:db8:abc:%s::100/120" % cnt
        port = len(subhosts)+2
        LOGGER.debug("set rule: ipv6_dst=%s -> fd=%s.%s", addr, net, port)
        _add_switch_rule(
            net, 1, len(subhosts)+1,
            ["ipv6_dst=%s" % addr],
            ["fd=%s.%s" % (net, port)]
        )

        # forwarding rule to firewall (default rule)
        LOGGER.debug("set rule: * -> fd=%s.1", net)
        _add_switch_rule(net, 1, 65535, commands=["fd=%s.1" % net])

        cnt += 1


def _add_subnet_routing_rules(cnt, subnets):
    for cnt in range(cnt, len(subnets)+1):
        LOGGER.debug("set rule: ipv6_dst=2001:db8:abc:%s::0/64 -> fd=pgf.%s", cnt, cnt)
        _add_switch_rule(
            "pgf",
            idx=1,
            fields=["ipv6_dst=2001:db8:abc:%s::0/64" % cnt],
            commands=["fd=pgf.%s" % cnt]
        )


def _create_dmz_hosts(cnt, hosts):
    only_ha = lambda x: x[:2]
    for host, addr in [only_ha(x) for x in hosts]:
        _add_host(cnt, host, "dmz", addr)
        cnt += 1


def _create_subnet_hosts(cnt, subnets, subhosts):
    for net in subnets:
        LOGGER.info("  creating host %s... ", net)

        srv = 0
        for host in subhosts:
            port = srv + 2
            addr = "2001:db8:abc:%s::%s" % (cnt, srv+1)
            _add_host(port, host, net, addr)
            srv += 1

        LOGGER.info("  created host %s.", net)

        cnt += 1


def _create_subnet_clients(cnt, subnets, subhosts):
    for net in subnets:
        LOGGER.info("  creating client %s... ", net)

        port = len(subhosts)+2
        addr = "2001:db8:abc:%s::100/120" % cnt
        _add_host(port, "clients", net, addr)

        LOGGER.info("  created client %s.", net)

        cnt += 1


def _add_host(port, host, net, addr):
    hname = host[0] if isinstance(host, tuple) else host
    hostnet = "%s.%s" % (hname, net)
    nethost = "%s-%s" % (net, hname)
    server = "source.%s" % hostnet

    _add_packet_filter(hostnet, addr, 1)

    _link_ports([
        ("%s.2"%hostnet, "%s.%s"%(net, port)),
        ("%s.%s"%(net, port), "%s.1"%hostnet)
    ])

    _add_generator(server, ["ipv6_src=%s" % addr])

    _add_ruleset(hostnet, 1, addr, "%s/%s-ruleset" % (RULESETS, nethost))

    _link_ports([("%s.1"%server, "%s_output_states_in"%hostnet)])

    LOGGER.debug("\tset rule: * -> fd=%s.%s", hostnet, 1)
    _add_switch_rule(hostnet, 1, 1, [], ["fd=%s.%s" % (hostnet, 1)])


def _test_subnet(net, hosts=None):
    hosts = hosts if hosts is not None else []

    LOGGER.info("    testing %s... ", net)

    for host in hosts:
        _test_host(host, net)

    _test_clients(net)

    LOGGER.info("    tested %s.", net)


def _test_host(host, net):
    hname = "%s.%s" % (host[0] if isinstance(host, tuple) else host, net)
    server = "probe.%s" % hname

    # add probe that looks for incoming flows for tcp port 22 (ssh)
    # originating from the internet
    _add_probe(
        server,
        "existential",
        filter_fields=["tcp_dst=22"],
        test_path=[".*(p=pgf.1);$"]
    )

    # link probe to host packet filter
    _link_ports([("%s_input_states_accept"%hname, "%s.1"%server)])
    _link_ports([("%s_input_rules_accept"%hname, "%s.1"%server)])


def _test_clients(net):
    cname = "clients.%s" % net
    clients = "probe.%s" % cname

    # add probe that looks for incoming flows originating from the internet
    _add_probe(
        clients,
        "existential",
        test_path=[".*(p=pgf.1);$"]
    )

    # link probe to host packet filter
    _link_ports([("%s_input_states_accept"%cname, "%s.1"%clients)])
    _link_ports([("%s_input_rules_accept"%cname, "%s.1"%clients)])


def _test_dmz(hosts):
    only_host = lambda x: x[0]
    for hname in [only_host(x) for x in hosts]:
        _test_host(hname, "dmz")

RULESETS = "bench/wl-ad6-rulesets"
AD6 = (
    [
        ("file", "2001:db8:abc:0::1", ["tcp:21", "tcp:115", "tcp:22", "udp:22"]),
        ("mail", "2001:db8:abc:0::2", [
            "tcp:25", "tcp:587", "tcp:110", "tcp:143", "tcp:220", "tcp:465",
            "tcp:993", "tcp:995", "udp:143", "udp:220", "tcp:22", "udp:22"
        ]),
        ("web", "2001:db8:abc:0::3", ["tcp:80", "tcp:443", "tcp:22", "udp:22"]),
        ("ldap", "2001:db8:abc:0::4", [
            "tcp:389", "tcp:636", "udp:389", "udp:123", "tcp:22", "udp:22"
        ]),
        ("vpn", "2001:db8:abc:0::5", [
            "tcp:1194", "tcp:1723", "udp:1194", "udp:1723", "tcp:22", "udp:22"
        ]),
        ("dns", "2001:db8:abc:0::6", ["tcp:53", "udp:53", "tcp:22", "udp:22"]),
        ("data", "2001:db8:abc:0::7", [
            "tcp:118", "tcp:156", "tcp:22", "udp:118", "udp:156", "udp:22"
        ]),
        ("adm", "2001:db8:abc:0::8", ["udp:161", "tcp:22", "udp:22"])
    ],
    [
        "api",
        "asta",
        "botanischer-garten-potsdam.de",
        "chem",
        "cs",
        "geo",
        "geographie",
        "hgp-potsdam.de",
        "hpi",
        "hssport",
        "intern",
        "jura",
#        "ling",
#        "math",
#        "mmz-potsdam.de",
#        "physik",
#        "pogs",
#        "psych",
#        "sq-brandenburg.de",
#        "ub",
        "welcome-center-potsdam.de"
    ],
    [
        ("web", ["tcp:80", "tcp:443", "tcp:22", "udp:22"]),
        ("voip", ["tcp:5060", "tcp:5061", "udp:5060", "tcp:22", "udp:22"]),
        ("print", ["tcp:631", "tcp:22", "udp:631", "udp:22"]),
        ("mail", [
            "tcp:25", "tcp:587", "tcp:110", "tcp:143", "tcp:220", "tcp:465",
            "tcp:993", "tcp:995", "tcp:22", "udp:143", "udp:220", "udp:22"
        ]),
        ("file", [
            "tcp:137", "tcp:138", "tcp:139", "tcp:445", "tcp:2049", "tcp:22",
            "udp:137", "udp:138", "udp:139", "udp:22"
        ])
    ]
)


def campus_network(config):
    """ Benchmarks FaVe using the a campus network styled workload including a
        central firewall, a DMZ, a campus wifi, and some generic branch
        networks.
    """

    hosts, subnets, subhosts = config

    # build topology
    LOGGER.info("reading topology...")
    LOGGER.info("creating pgf... ")
    _add_packet_filter("pgf", "2001:db8:abc::1", 24)
    LOGGER.info("created pgf.")

    # create dmz
    LOGGER.info("creating dmz...")
    _add_switch("dmz", 9)
    _link_ports([("pgf.26", "dmz.1"), ["dmz.1", "pgf.2"]])
    LOGGER.info("created dmz")

    # create wifi
    LOGGER.info("creating wifi... ")
    _add_switch("wifi", 2)
    _link_ports([("pgf.3", "wifi.1"), ("wifi.1", "pgf.27")])
    LOGGER.info("created wifi.")

    # create subnets
    LOGGER.info("creating subnets...")
    _create_subnet_switches(4, subnets, subhosts)

    # populate firewall
    LOGGER.info("populating firewall...")
    _add_ruleset("pgf", 24, "2001:db8:abc::1", "%s/pgf-ruleset" % RULESETS)
    #_add_ruleset("pgf", "2001:db8:abc::1", "%s/simple-ruleset" % RULESETS)

    # dmz (route)
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:0::0/64 -> fd=pgf.2")
    _add_switch_rule("pgf", 1, 1, ["ipv6_dst=2001:db8:abc:0::0/64"], ["fd=pgf.2"])

    # wifi (route)
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:1::0/64 -> fd=pgf.3")
    _add_switch_rule("pgf", 1, 1, ["ipv6_dst=2001:db8:abc:1::0/64"], ["fd=pgf.3"])

    # subnets (routes)
    _add_subnet_routing_rules(4, subnets)

    LOGGER.info("populated firewall.")

    LOGGER.info("populating switches...")
    # dmz
    _set_dmz_switch_rules(2, hosts)

    # forwarding rule to firewall (default rule)
    LOGGER.debug("\tset rule: * -> fd=dmz.1")
    _add_switch_rule("dmz", 1, 65535, commands=["fd=dmz.1"])

    # wifi
    # forwarding rule to client
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:1::0/64 -> fd=wifi.2")
    _add_switch_rule("wifi", 1, 1, ["ipv6_dst=2001:db8:abc:1::0/64"], ["fd=wifi.2"])

    # forwarding rule to firewall (default rule)
    LOGGER.debug("\tset rule: * -> fd=wifi.1")
    _add_switch_rule("wifi", 1, 65535, commands=["fd=wifi.1"])

    # subnets
    _set_subnet_switch_rules(4, subnets, subhosts)
    LOGGER.info("populated switches")

    LOGGER.info("creating internet (source)...")
    _add_generator("internet")
    _link_ports([("internet.1", "pgf.1"), ("pgf.25", "internet.1")])
    LOGGER.info("created internet.")

    LOGGER.info("creating hosts (pf + source) in dmz...")
    _create_dmz_hosts(2, hosts)
    LOGGER.info("created hosts (pf + source) in dmz.")

    LOGGER.info("creating hosts (pf + source) in subnets...")
    _create_subnet_hosts(4, subnets, subhosts)

    LOGGER.info("creating clients (pf + source) in subnets...")
    _create_subnet_clients(4, subnets, subhosts)

    LOGGER.info("testing ssh reachability from the internet...")
    LOGGER.info("  testing dmz... ")
    _test_dmz(hosts)
    LOGGER.info("  tested dmz.")

    LOGGER.info("  testing subnets...")
    for net in subnets:
        _test_subnet(net, hosts=subhosts)


def _generate_reachability_tests(config):
    """ XXX flow tests:
    Internet <--> PublicHosts - ok
    Internet ---> PublicSubHosts
    Internet !--> PrivateSubHosts - (ok)
    PublicHost ---> PublicHosts - ok
    PublicSubHosts ---> PublicSubHosts
    PrivateSubHosts(X) <->> PrivateSubHosts(X)
    PrivateSubHosts(X) !--> PrivateSubHosts(Y) - (ok)
    SubClients <->> Internet - (ok)
    SubClients <->> PublicHosts - (ok)
    SubClients <->> PublicSubHosts (ok)
    SubClients <->> PrivateSubHosts (ok)
    SubClients(X) !--> SubClients(Y) - ok
    """

    tests = []
    hosts, subnets, subhosts = config

    label = lambda x: x[0]

    for host in hosts:
        hlabel = label(host)
        # public servers may be reached from the internet
        tests.append("s=internet && EF p=probe.%s.dmz" % hlabel)
        # public servers may reach the internet, TODO: allow stateful
        tests.append("! s=source.%s.dmz && EF s=internet" % hlabel)
        # public servers may reach each other
        tests.extend([
            "s=source.%s.dmz && EF p=probe.%s.dmz" % (
                hlabel,
                label(h)
            ) for h in hosts if label(h) != hlabel
        ])

    for subnet in subnets:
        # clients may reach the internet
#        tests.append("s=client.%s && EF p=internet" % subnet)

        # clients may not be reached from the internet, TODO: allow stateful
#        tests.append("! s=internet && EF p=clients.%s" % subnet)

        # clients may reach public servers
#        tests.extend([
#            "s=clients.%s && EF p=%s" % (
#                subnet,
#                label(h)
#            ) for h in hosts
#        ])

        # public hosts may not reach internal clients, TODO: allow stateful
#        tests.extend([
#            "! s=%s && EF p=clients.%s" % (label(h), subnet) for h in hosts
#        ])

        # internal clients may reach internal servers
#        tests.extend([
#            "s=clients.%s && EF p=%s.%s" % (
#                subnet,
#                subhost,
#                subnet
#            ) for subhost in subhosts
#        ])

        # internal servers may not reach internal clients, TODO: allow stateful
#        tests.extend([
#            "! s=%s.%s && EF p=clients.%s" % (
#                label(subhost),
#                subnet,
#                subnet
#            ) for subhost in subhosts
#        ])

        # internal clients may not reach other subnet's internal clients
#        tests.extend([
#            "! s=clients.%s %% EF p=clients.%s" % (
#                osn,
#                subnet
#            ) for osn in subnets if osn != subnet
#        ])

        # other subnet's internal clients may not reach internal clients
#        tests.extend([
#            "! s=clients.%s && EF p=clients.%s" % (
#                osn,
#                subnet
#            ) for osn in subnets if osn != subnet
#        ])

        # the internet may not reach internal servers
        tests.extend([
            "! s=internet && EF p=probe.%s.%s" % (
                label(subhost),
                subnet
            ) for subhost in subhosts
        ])
        # internal servers may not reach the internet
        tests.extend([
            "! s=source.%s.%s && EF s=internet" % (
                label(subhost),
                subnet
            ) for subhost in subhosts
        ])

        # internal servers may not reach other subnet's internal servers
        tests.extend([
            "! s=source.%s.%s && EF p=probe.%s.%s" % (
                subhost,
                subnet,
                osh,
                osn
            ) for subhost, osh, osn in [(
                label(x),
                label(y),
                z
            ) for x in subhosts for y in subhosts for z in subnets if label(x) != label(y)]
        ])

    stests = iter(sorted(tests))
    prev = stests.next()
    cnt = 0
    for next in stests:
        if prev == next:
            cnt += 1
            print "  duplicate: %s" % prev
        prev = next
    print "number of tests:\t%s\nduplicates:\t%s" % (len(tests), cnt)

    return tests


if __name__ == "__main__":
    LOGGER.info("starting netplumber...")
    os.system("scripts/start_np.sh bench/wl-ad6-np.conf")
    LOGGER.info("started netplumber.")

    LOGGER.info("starting aggregator...")
    os.system("scripts/start_aggr.sh")
    LOGGER.info("started aggregator.")

    campus_network(AD6)

    LOGGER.info("dumping fave and netplumber...")
    dumper.main(["-anpt"])
    LOGGER.info("dumped fave and netplumber.")

    LOGGER.info("checking flow trees...")
    tests = _generate_reachability_tests(AD6)
    checker.main(["-c", ";".join(tests)])
    LOGGER.info("checked flow trees.")

    LOGGER.info("stopping fave and netplumber...")
    os.system("bash scripts/stop_fave.sh")
    LOGGER.info("stopped fave and netplumber.")
