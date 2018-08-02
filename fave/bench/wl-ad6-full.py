#!/usr/bin/env python2

import os
import sys

import logging

from topology import topology as topo
from ip6np import ip6np as ip6tables
from openflow import switch

import time

import netplumber.dump_np as dumper
import netplumber.print_np as printer

LOGGER = logging.getLogger("ad6")
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.DEBUG)

def measure(function,logger):
    t_start = time.time()
    function()
    t_end = time.time()

    logger.info("%fms" % ((t_end-t_start)*1000.0))


def main():
    TMPDIR="/tmp/np"
    os.system("mkdir -p %s" % TMPDIR)

    LOGGER.info("deleting old logs and measurements...")
    os.system("rm -f /tmp/np/*.log")
    LOGGER.info("deleted old logs and measurements.")

    logging.basicConfig(
        format='%(asctime)s [%(name)s.%(levelname)s] - %(message)s',
        level=logging.INFO,
        filename="%s/fave.log" % TMPDIR,
        filemode='w'
    )

    log_handler = logging.FileHandler("%s/fave.log" % TMPDIR)
#    log_handler.setFormatter(
#        logging.Formatter('%(asctime)s %(levelname)s %(message)s')
#    )

    pf_logger = logging.getLogger("pf")
    pf_logger.addHandler(log_handler)
    pf_logger.setLevel(logging.INFO)

    pfr_logger = logging.getLogger("pfr")
    pfr_logger.addHandler(log_handler)
    pfr_logger.setLevel(logging.INFO)

    sub_logger = logging.getLogger("sub")
    sub_logger.addHandler(log_handler)
    sub_logger.setLevel(logging.INFO)

    subl_logger = logging.getLogger("subl")
    subl_logger.addHandler(log_handler)
    subl_logger.setLevel(logging.INFO)

    sw_logger = logging.getLogger("sw")
    sw_logger.addHandler(log_handler)
    sw_logger.setLevel(logging.INFO)

    src_logger = logging.getLogger("src")
    src_logger.addHandler(log_handler)
    src_logger.setLevel(logging.INFO)

    srcl_logger = logging.getLogger("srcl")
    srcl_logger.addHandler(log_handler)
    srcl_logger.setLevel(logging.INFO)

    probe_logger = logging.getLogger("probe")
    probe_logger.addHandler(log_handler)
    probe_logger.setLevel(logging.INFO)

    probel_logger = logging.getLogger("probel")
    probel_logger.addHandler(log_handler)
    probel_logger.setLevel(logging.INFO)

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

    measure(
        lambda: topo.main([
            "-a",
            "-t","packet_filter",
            "-n","pgf",
            "-i","2001:db8:abc::1",
            "-p","24"
        ]),
        pf_logger
    )
    LOGGER.info("created pgf.")

    # create dmz
    LOGGER.info("creating dmz... ")
    measure(
        lambda: topo.main(["-a","-t","switch","-n","dmz","-p","9"]),
        sub_logger
    )
    measure(
        lambda: topo.main(["-a","-l","pgf.26:dmz.1,dmz.1:pgf.2"]),
        subl_logger
    )
    LOGGER.info("created dmz")

    hosts = [
        ("file","2001:db8:abc:0::1",["tcp:21","tcp:115","tcp:22","udp:22"]),
        ("mail","2001:db8:abc:0::2",[
            "tcp:25","tcp:587","tcp:110","tcp:143","tcp:220","tcp:465",
            "tcp:993","tcp:995","udp:143","udp:220","tcp:22","udp:22"
        ]),
        ("web","2001:db8:abc:0::3",["tcp:80","tcp:443","tcp:22","udp:22"]),
        ("ldap","2001:db8:abc:0::4",[
            "tcp:389","tcp:636","udp:389","udp:123","tcp:22","udp:22"
        ]),
        ("vpn","2001:db8:abc:0::5",[
            "tcp:1194","tcp:1723","udp:1194","udp:1723","tcp:22","udp:22"
        ]),
        ("dns","2001:db8:abc:0::6",["tcp:53","udp:53","tcp:22","udp:22"]),
        ("data","2001:db8:abc:0::7",[
            "tcp:118","tcp:156","tcp:22","udp:118","udp:156","udp:22"
        ]),
        ("adm","2001:db8:abc:0::8",["udp:161","tcp:22","udp:22"])
    ]

    # create wifi
    LOGGER.info("creating wifi... ")
    measure(
        lambda: topo.main(["-a","-t","switch","-n","wifi","-p","2"]),
        sub_logger
    )
    measure(
        lambda: topo.main(["-a","-l","pgf.3:wifi.1,wifi.1:pgf.27"]),
        subl_logger
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
        ("web",["tcp:80","tcp:443","tcp:22","udp:22"]),
        ("voip",["tcp:5060","tcp:5061","udp:5060","tcp:22","udp:22"]),
        ("print",["tcp:631","tcp:22","udp:631","udp:22"]),
        ("mail",[
            "tcp:25","tcp:587","tcp:110","tcp:143","tcp:220","tcp:465",
            "tcp:993","tcp:995","tcp:22","udp:143","udp:220","udp:22"
        ]),
        ("file",[
            "tcp:137","tcp:138","tcp:139","tcp:445","tcp:2049","tcp:22",
            "udp:137","udp:138","udp:139","udp:22"
        ])
    ]

    cnt=4
    for net in subnets:
        LOGGER.info("  creating subnet %s...", net)

        # create switch for subnet
        measure(
            lambda: topo.main(["-a","-t","switch","-n",net,"-p","7"]),
            sub_logger
        )

        # link switch to firewall
        measure(
            lambda: topo.main([
                "-a",
                "-l","pgf.%s:%s.1,%s.1:pgf.%s" % (cnt+24,net,net,cnt)
            ]),
            subl_logger
        )

        LOGGER.info("  created subnet %s.", net)

        cnt += 1

    # populate firewall
    LOGGER.info("populating firewall...")

    measure(
        lambda: ip6tables.main([
            "-n","pgf","-i","2001:db8:abc::1","-f","rulesets/pgf-ruleset"
        ]),
        pfr_logger
    )

    # dmz (route)
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:0::0/64 -> fd=pgf.2")
    measure(
        lambda: switch.main([
            "-a",
            "-i","1",
            "-n","pgf",
            "-t","1",
            "-f","ipv6_dst=2001:db8:abc:0::0/64",
            "-c","fd=pgf.2"
        ]),
        sw_logger
    )

    # wifi (route)
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:1::0/64 -> fd=pgf.3")
    measure(
        lambda: switch.main([
            "-a",
            "-i","1",
            "-n","pgf",
            "-t","1",
            "-f","ipv6_dst=2001:db8:abc:1::0/64",
            "-c", "fd=pgf.3"
        ]),
        sw_logger
    )

    # subnets (routes)
    cnt = 4
    for net in subnets:
        LOGGER.debug("set rule: ipv6_dst=2001:db8:abc:%s::0/64 -> fd=pgf.%s", cnt,cnt)
        measure(
            lambda: switch.main([
                "-a",
                "-i","1",
                "-n","pgf",
                "-f","ipv6_dst=2001:db8:abc:%s::0/64" % cnt,
                "-c","fd=pgf.%s" % cnt
            ]),
            sw_logger
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
            lambda: switch.main([
                "-a",
                "-i","1",
                "-n","dmz",
                "-t","1",
                "-f","ipv6_dst=%s" % addr,
                "-c","fd=dmz.%s" % cnt
            ]),
            sw_logger
        )

        cnt += 1

    # forwarding rule to firewall (default rule)
    LOGGER.debug("\tset rule: * -> fd=dmz.1")
    measure(
        lambda: switch.main(["-a","-i","10","-n","dmz","-t","1","-c","fd=dmz.1"]),
        sw_logger
    )

    # wifi
    # forwarding rule to client
    LOGGER.debug("\tset rule: ipv6_dst=2001:db8:abc:1::0/64 -> fd=wifi.2")
    measure(
        lambda: switch.main([
            "-a",
            "-i","1",
            "-n","wifi",
            "-t","1",
            "-f","ipv6_dst=2001:db8:abc:1::0/64",
            "-c","fd=wifi.2"
        ]),
        sw_logger
    )

    # forwarding rule to firewall (default rule)
    LOGGER.debug("\tset rule: * -> fd=wifi.1")
    measure(
        lambda: switch.main(["-a","-i","1","-n","wifi","-t","1","-c","fd=wifi.1"]),
        sw_logger
    )

    # subnets
    cnt = 4
    for net in subnets:
        srv = 1

        for host in subhosts:
            ident = srv
            srv += 1
            port = srv

            server = "%s.%s" % (host[0],net)
            addr = "2001:db8:abc:%s::%s" % (cnt,ident)

            # forwarding rule to server
            LOGGER.debug("set rule: ipv6_dst=%s -> fd=%s.%s", addr,net,port)
            measure(
                lambda: switch.main([
                    "-a",
                    "-i","1",
                    "-n",net,
                    "-t","1",
                    "-f","ipv6_dst=%s" % addr,
                    "-c","fd=%s.%s" % (net,port)
                ]),
                sw_logger
            )

        # forwarding rule to firewall (default rule)
        LOGGER.debug("set rule: * -> fd=%s.1", net)
        measure(
            lambda: switch.main([
                "-a","-i","1","-n",net,"-t","1","-c","fd=%s.1" % net
            ]),
            sw_logger
        )
    LOGGER.info("populated switches")

    LOGGER.info("creating internet (source)...")
    measure(
        lambda: topo.main(["-a","-t","generator","-n","internet"]),
        src_logger
    )
    measure(
        lambda: topo.main(["-a","-l","internet.1:pgf.1,pgf.25:internet.1"]),
        srcl_logger
    )
    LOGGER.info("created internet.")

    LOGGER.info("creating hosts (pf + source) in dmz...")
    cnt = 2
    for  h,a,p in hosts:
        measure(
            lambda: topo.main(["-a","-t","packet_filter","-n",h,"-i",a,"-p","1"]),
            pf_logger
        )

        measure(
            lambda: topo.main([
                "-a",
                "-l","%s.2:dmz.%s,dmz.%s:%s.1" % (h,cnt,cnt,h)
            ]),
            subl_logger
        )

        measure(
            lambda: topo.main([
                "-a",
                "-t","generator",
                "-n","source.%s" % h,
                "-f","ipv6_src=%s" % a
            ]),
            src_logger
        )

        measure(
            lambda: ip6tables.main(["-n",h,"-i",a,"-f","rulesets/%s-ruleset" % h]),
            pfr_logger
        )

        measure(
            lambda: topo.main([
                "-a",
                "-l","source.%s.1:%s_output_states_in" % (h,h)
            ]),
            srcl_logger
        )

        # forwarding rule to switch
        LOGGER.debug("\tset rule: * -> fd=%s.%s",h,1)
        measure(
            lambda: switch.main([
                "-a",
                "-i","1",
                "-n",h,
                "-t","1",
                "-c","fd=%s.%s" % (h,1)
            ]),
            pfr_logger
        )

        cnt += 1

    LOGGER.info("created hosts (pf + source) in dmz.")

    LOGGER.info("creating hosts (pf + source) in subnets...")
    cnt = 4

    for net in subnets:
        LOGGER.info("  creating host %s... ", net)

        srv = 0
        for host in subhosts:
            port = srv + 2
            hn = "%s.%s" % (host[0],net)
            nh = "%s-%s" % (net,host[0])
            server = "source.%s" % hn
            addr = "2001:db8:abc:%s::%s" % (cnt,srv+1)

            measure(
                lambda: topo.main([
                    "-a",
                    "-t","packet_filter",
                    "-n",hn,
                    "-i",addr,
                    "-p","1"
                ]),
                pf_logger
            )

            measure(
                lambda: topo.main([
                    "-a",
                    "-l","%s.2:%s.%s,%s.%s:%s.1" % (hn,net,port,net,port,hn)
                ]),
                subl_logger
            )

            measure(
                lambda: topo.main([
                    "-a","-t","generator","-n",server,"-f","ipv6_src=%s" % addr
                ]),
                src_logger
            )

            measure(
                lambda: ip6tables.main(["-n",hn,"-i",addr,"-f","rulesets/%s-ruleset" % nh]),
                pfr_logger
            )

            measure(
                lambda: topo.main(["-a","-l","%s.1:%s_output_states_in" % (server,hn)]),
                srcl_logger
            )

            LOGGER.debug("\tset rule: * -> fd=%s.%s",hn,1)
            measure(
                lambda: switch.main([
                    "-a",
                    "-i","1",
                    "-n",hn,
                    "-t","1",
                    "-c","fd=%s.%s" % (hn,1)
                ]),
                src_logger
            )

            srv += 1

        LOGGER.info("created host %s.", net)

        cnt += 1
    LOGGER.info("testing ssh reachability from the internet...")

    LOGGER.info("  testing dmz... ")
    cnt = 2
    for h,a,p in hosts:

        # add probe that looks for incoming flows for tcp port 22 (ssh) originating from the internet
        measure(
            lambda: topo.main([
                "-a",
                "-t","probe",
                "-n","probe.%s" % h,
                "-q","existential",
                "-P",".*(p=pgf.1);$",
                "-F","tcp_dst=22"
            ]),
            probe_logger
        )
        # link probe to host input
        measure(
            lambda: topo.main(["-a","-l","%s_input_states_accept:probe.%s.1" % (h,h)]),
            probel_logger
        )
        measure(
            lambda: topo.main(["-a","-l","%s_input_rules_accept:probe.%s.1" % (h,h)]),
            probel_logger
        )

        # remove probe
        #PYTHONPATH=. $TIME -ao $PROBELOG python2 topology/topology.py -d -n $H
        # ... and link
        #PYTHONPATH=. $TIME -ao $PROBELLOG python2 topology/topology.py -d -l $H.1:dmz.$cnt

        cnt += 1
    LOGGER.info("tested dmz.")

    LOGGER.info("  testing subnets...")
    cnt = 4
    for net in subnets:
        srv = 1

        LOGGER.info("    testing %s... ", net)

        for host in subhosts:
            port = srv + 1
            hn = "%s.%s" % (host[0],net)
            server = "probe.%s" % hn
            addr="2001:db8:abc:%s::%s" % (cnt,srv)

            # add probe that looks for incoming flows for tcp port 22 (ssh) originating from the internet
            measure(
                lambda: topo.main([
                    "-a",
                    "-t","probe",
                    "-n",server,
                    "-q","existential",
                    "-P",".*(p=pgf.1);$",
                    "-F","tcp_dst=22"
                ]),
                probe_logger
            )
            # link probe to switch
            measure(
                lambda: topo.main([
                    "-a","-l","%s_input_states_accept:%s.1" % (hn,server)
                ]),
                probel_logger
            )
            measure(
                lambda: topo.main([
                    "-a","-l","%s_input_rules_accept:%s.1" % (hn,server)
                ]),
                probel_logger
            )

        LOGGER.info("tested %s.", net)

        cnt += 1

    dumper.main(["-anpf"])

    LOGGER.info("stopping fave and netplumber...")
    os.system("scripts/stop_fave.sh")
    LOGGER.info("stopped fave and netplumber.")

if __name__ == "__main__":
    main()
