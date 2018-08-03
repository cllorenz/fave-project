#!/usr/bin/env python2

""" This module benchmarks FaVe with the AD6 workload.
"""

import os
import sys
import logging
import time

import netplumber.dump_np as dumper
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

SUBL_LOGGER = logging.getLogger("subl")
SUBL_LOGGER.addHandler(LOG_HANDLER)
SUBL_LOGGER.setLevel(logging.INFO)

SW_LOGGER = logging.getLogger("sw")
SW_LOGGER.addHandler(LOG_HANDLER)
SW_LOGGER.setLevel(logging.INFO)

SRC_LOGGER = logging.getLogger("src")
SRC_LOGGER.addHandler(LOG_HANDLER)
SRC_LOGGER.setLevel(logging.INFO)

SRCL_LOGGER = logging.getLogger("srcl")
SRCL_LOGGER.addHandler(LOG_HANDLER)
SRCL_LOGGER.setLevel(logging.INFO)

PROBE_LOGGER = logging.getLogger("probe")
PROBE_LOGGER.addHandler(LOG_HANDLER)
PROBE_LOGGER.setLevel(logging.INFO)

PROBEL_LOGGER = logging.getLogger("probel")
PROBEL_LOGGER.addHandler(LOG_HANDLER)
PROBEL_LOGGER.setLevel(logging.INFO)


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


def main():
    """ Benchmarks FaVe using the AD6 workload.
    """

#    PFLOG=$TMPDIR/pf.log
#    PFRLOG=$TMPDIR/pfr.log
#    SUBLOG=$TMPDIR/sub.log
#    SUBLLOG=$TMPDIR/subl.log
#    SWLOG=$TMPDIR/sw.log
#    SRCLOG=$TMPDIR/source.log
#    SRCLLOG=$TMPDIR/sourcel.log
#    PROBELOG=$TMPDIR/probe.log
#    PROBELLOG=$TMPDIR/probel.log

#TIME='/usr/bin/time -f %e'

    LOGGER.info("starting netplumber...")
    os.system("scripts/start_np.sh test-workload-ad6.conf")
    LOGGER.info("started netplumber.")

    LOGGER.info("starting aggregator...")
    os.system("scripts/start_aggr.sh")
    LOGGER.info("started aggregator.")

    # build topology
    LOGGER.info("reading topology...")
    LOGGER.info("creating pgf... ")
    _add_packet_filter("pgf", "2001:db8:abc::1", 24)
    LOGGER.info("created pgf.")

    # create dmz
    LOGGER.info("creating dmz...")
    _add_switch("dmz", 9)
    measure(
        lambda: topo.main(["-a", "-l", "pgf.26:dmz.1,dmz.1:pgf.2"]),
        SUBL_LOGGER
    )
    LOGGER.info("created dmz")

    hosts = [
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
    ]

    # create wifi
    LOGGER.info("creating wifi... ")
    _add_switch("wifi", 2)
    measure(
        lambda: topo.main(["-a", "-l", "pgf.3:wifi.1,wifi.1:pgf.27"]),
        SUBL_LOGGER
    )
    LOGGER.info("created wifi.")

    # create subnets
    LOGGER.info("creating subnets...")
    subnets = [
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
        "ling",
        "math",
        "mmz-potsdam.de",
        "physik",
        "pogs",
        "psych",
        "sq-brandenburg.de",
        "ub",
        "welcome-center-potsdam.de"
    ]

    subhosts = [
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

    cnt = 4
    for net in subnets:
        LOGGER.info("  creating subnet %s...", net)

        # create switch for subnet
        _add_switch(net, 7)

        # link switch to firewall
        measure(
            lambda n=net: topo.main([
                "-a",
                "-l", "pgf.%s:%s.1,%s.1:pgf.%s" % (cnt+24, n, n, cnt)
            ]),
            SUBL_LOGGER
        )

        LOGGER.info("  created subnet %s.", net)

        cnt += 1

    # populate firewall
    LOGGER.info("populating firewall...")

    measure(
        lambda: ip6tables.main([
            "-n", "pgf", "-i", "2001:db8:abc::1", "-f", "rulesets/pgf-ruleset"
        ]),
        PFR_LOGGER
    )

    # dmz (route)
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:0::0/64 -> fd=pgf.2")
    measure(
        lambda: switch.main([
            "-a",
            "-i", "1",
            "-n", "pgf",
            "-t", "1",
            "-f", "ipv6_dst=2001:db8:abc:0::0/64",
            "-c", "fd=pgf.2"
        ]),
        SW_LOGGER
    )

    # wifi (route)
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:1::0/64 -> fd=pgf.3")
    measure(
        lambda: switch.main([
            "-a",
            "-i", "1",
            "-n", "pgf",
            "-t", "1",
            "-f", "ipv6_dst=2001:db8:abc:1::0/64",
            "-c", "fd=pgf.3"
        ]),
        SW_LOGGER
    )

    # subnets (routes)
    cnt = 4
    for net in subnets:
        LOGGER.debug("set rule: ipv6_dst=2001:db8:abc:%s::0/64 -> fd=pgf.%s", cnt, cnt)
        measure(
            lambda: switch.main([
                "-a",
                "-i", "1",
                "-n", "pgf",
                "-f", "ipv6_dst=2001:db8:abc:%s::0/64" % cnt,
                "-c", "fd=pgf.%s" % cnt
            ]),
            SW_LOGGER
        )

        cnt += 1

    LOGGER.info("populated firewall.")

    LOGGER.info("populating switches...")

    # dmz
    cnt = 2
    for host in hosts:
        addr = host[1]

        # forwarding rule to host
        LOGGER.debug("\tset rule: ipv6_dst=%s -> fd=dmz.1", addr)
        measure(
            lambda a=addr: switch.main([
                "-a",
                "-i", "1",
                "-n", "dmz",
                "-t", "1",
                "-f", "ipv6_dst=%s" % a,
                "-c", "fd=dmz.%s" % cnt
            ]),
            SW_LOGGER
        )

        cnt += 1

    # forwarding rule to firewall (default rule)
    LOGGER.debug("\tset rule: * -> fd=dmz.1")
    measure(
        lambda: switch.main(["-a", "-i", "10", "-n", "dmz", "-t", "1", "-c", "fd=dmz.1"]),
        SW_LOGGER
    )

    # wifi
    # forwarding rule to client
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:1::0/64 -> fd=wifi.2")
    measure(
        lambda: switch.main([
            "-a",
            "-i", "1",
            "-n", "wifi",
            "-t", "1",
            "-f", "ipv6_dst=2001:db8:abc:1::0/64",
            "-c", "fd=wifi.2"
        ]),
        SW_LOGGER
    )

    # forwarding rule to firewall (default rule)
    LOGGER.debug("\tset rule: * -> fd=wifi.1")
    measure(
        lambda: switch.main(["-a", "-i", "1", "-n", "wifi", "-t", "1", "-c", "fd=wifi.1"]),
        SW_LOGGER
    )

    # subnets
    cnt = 4
    for net in subnets:
        srv = 1

        for host in subhosts:
            ident = srv
            srv += 1
            port = srv

            server = "%s.%s" % (host[0], net)
            addr = "2001:db8:abc:%s::%s" % (cnt, ident)

            # forwarding rule to server
            LOGGER.debug("set rule: ipv6_dst=%s -> fd=%s.%s", addr, net, port)
            measure(
                lambda n=net, a=addr, p=port: switch.main([
                    "-a",
                    "-i", "1",
                    "-n", n,
                    "-t", "1",
                    "-f", "ipv6_dst=%s" % a,
                    "-c", "fd=%s.%s" % (n, p)
                ]),
                SW_LOGGER
            )

        # forwarding rule to firewall (default rule)
        LOGGER.debug("set rule: * -> fd=%s.1", net)
        measure(
            lambda n=net: switch.main([
                "-a", "-i", "1", "-n", n, "-t", "1", "-c", "fd=%s.1" % n
            ]),
            SW_LOGGER
        )
    LOGGER.info("populated switches")

    LOGGER.info("creating internet (source)...")
    measure(
        lambda: topo.main(["-a", "-t", "generator", "-n", "internet"]),
        SRC_LOGGER
    )
    measure(
        lambda: topo.main(["-a", "-l", "internet.1:pgf.1,pgf.25:internet.1"]),
        SRCL_LOGGER
    )
    LOGGER.info("created internet.")

    LOGGER.info("creating hosts (pf + source) in dmz...")
    cnt = 2
    only_ha = lambda x: x[:2]
    for host, addr in [only_ha(x) for x in hosts]:
        _add_host(cnt, host, "dmz", addr)
        cnt += 1

    LOGGER.info("created hosts (pf + source) in dmz.")

    LOGGER.info("creating hosts (pf + source) in subnets...")
    cnt = 4

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

    LOGGER.info("testing ssh reachability from the internet...")

    LOGGER.info("  testing dmz... ")
    only_ha = lambda x: x[:2]
    for hname, addr in [only_ha(x) for x in hosts]:
        _test_host(hname, "dmz")

        # remove probe
        #PYTHONPATH=. $TIME -ao $PROBELOG python2 topology/topology.py -d -n $H
        # ... and link
        #PYTHONPATH=. $TIME -ao $PROBELLOG python2 topology/topology.py -d -l $H.1:dmz.$cnt

    LOGGER.info("  tested dmz.")

    LOGGER.info("  testing subnets...")
    for net in subnets:
        _test_subnet(net, hosts=subhosts)

    LOGGER.info("dumping fave and netplumber...")
    dumper.main(["-anpf"])
    LOGGER.info("dumped fave and netplumber.")

    LOGGER.info("stopping fave and netplumber...")
    os.system("scripts/stop_fave.sh")
    LOGGER.info("stopped fave and netplumber.")

    return


def _add_host(port, host, net, addr):
    hname = host[0] if isinstance(host, tuple) else host
    hostnet = "%s.%s" % (hname, net)
    nethost = "%s-%s" % (net, hname)
    server = "source.%s" % hostnet

    _add_packet_filter(hostnet, addr, 1)

    measure(
        lambda hn=hostnet, n=net: topo.main([
            "-a",
            "-l", "%s.2:%s.%s,%s.%s:%s.1" % (hn, n, port, n, port, hn)
        ]),
        SUBL_LOGGER
    )

    measure(
        lambda: topo.main([
            "-a", "-t", "generator", "-n", server, "-f", "ipv6_src=%s" % addr
        ]),
        SRC_LOGGER
    )

    measure(
        lambda hn=hostnet, nh=nethost: ip6tables.main(
            ["-n", hn, "-i", addr, "-f", "rulesets/%s-ruleset" % nh]
        ),
        PFR_LOGGER
    )

    measure(
        lambda hn=hostnet: topo.main(
            ["-a", "-l", "%s.1:%s_output_states_in" % (server, hn)]
        ),
        SRCL_LOGGER
    )

    LOGGER.debug("\tset rule: * -> fd=%s.%s", hostnet, 1)
    measure(
        lambda hn=hostnet: switch.main([
            "-a",
            "-i", "1",
            "-n", hn,
            "-t", "1",
            "-c", "fd=%s.%s" % (hn, 1)
        ]),
        SRC_LOGGER
    )


def _test_subnet(net, hosts=None):
    hosts = hosts if hosts is not None else []

    LOGGER.info("    testing %s... ", net)

    for host in hosts:
        _test_host(host, net)

    LOGGER.info("tested %s.", net)


def _test_host(host, net):
    hname = "%s.%s" % (host[0] if isinstance(host, tuple) else host, net)
    server = "probe.%s" % hname

    # add probe that looks for incoming flows for tcp port 22 (ssh)
    # originating from the internet
    measure(
        lambda: topo.main([
            "-a",
            "-t", "probe",
            "-n", server,
            "-q", "existential",
            "-P", ".*(p=pgf.1);$",
            "-F", "tcp_dst=22"
        ]),
        PROBE_LOGGER
    )
    # link probe to switch
    measure(
        lambda: topo.main([
            "-a", "-l", "%s_input_states_accept:%s.1" % (hname, server)
        ]),
        PROBEL_LOGGER
    )
    measure(
        lambda: topo.main([
            "-a", "-l", "%s_input_rules_accept:%s.1" % (hname, server)
        ]),
        PROBEL_LOGGER
    )


if __name__ == "__main__":
    main()
