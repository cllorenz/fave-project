#!/usr/bin/env python2

""" This module benchmarks FaVe using an generic workload.
"""

import random
import json
import os
import time
import argparse
import sys

from util.aggregator_utils import connect_to_fave, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX, fave_sendmsg
from ip6np.snapshot_packet_filter import StateCommand
from openflow.rule import SwitchRule, Match, SwitchRuleField, Forward
from bench.bench_utils import create_topology, add_routes, add_sources, add_policies

def _random_port():
    return random.randint(0, 65535)

def _random_ipv6_address():
    return ':'.join(["{:04x}".format(random.randint(0, 65535)) for _i in range(8)])

def _generate_request(node, i):
    rule = SwitchRule(
        node,
        node+'.forward_state',
        i,
        in_ports=[node+'.forward_state_in'],
        match=Match([
            SwitchRuleField('packet.ipv6.source', _random_ipv6_address()),
            SwitchRuleField('packet.ipv6.destination', '2001:db8::1'),
            SwitchRuleField('packet.ipv6.proto', 'tcp'),
            SwitchRuleField('packet.upper.sport', _random_port()),
            SwitchRuleField('packet.upper.dport', 80)
        ]),
        actions=[Forward(ports=[node+'.forward_state_accept'])]
    )
    req = StateCommand(node, 'add_state', [rule])

    return json.dumps(req.to_json())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-f', '--frequency', 
        type=int, dest="frequency", default=10, 
        help="the number of requests per second in Hertz (default: 10)"
    )
    parser.add_argument(
        '-d', '--duration',
        type=int, dest="duration", default=5,
        help="the duration of the run in seconds (default: 5)"
    )
    parser.add_argument(
        '-p', '--with_policy',
        dest="with_policy", action="store_true", default=False,
        help="include more complex network with two sources and two probes attached to the packet filter"
    )
    parser.add_argument(
        '-v', '--verbose',
        dest="verbose", action="store_true", default=False,
        help="show more status output"
    )
    parser.add_argument(
        '-t', '--use_tcp',
        dest="use_tcp", action="store_true", default=False,
        help="use tcp for connections to fave"
    )

    args = parser.parse_args(sys.argv[1:])

    no_req = args.frequency
    duration = args.duration
    with_policy = args.with_policy
    verbose = args.verbose
    use_unix = not args.use_tcp

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    os.system("bash scripts/start_np.sh -l bench/wl_state_snapshots/np.conf %s" % (
        "-u /dev/shm/np1.socket" if use_unix else "-s 127.0.0.1 -p 44001")
    )
    os.system("bash scripts/start_aggr.sh -d -S %s %s" % (
        "/dev/shm/np1.socket" if use_unix else "127.0.0.1:44001",
        "-u" if use_unix else ""
    ))

    if verbose: print "Initialize topology..."
    devices = [
        (
            "fw0",
            "snapshot_packet_filter",
            ["eth0", "eth1"],
            "2001:db8::1",
            "bench/wl_state_snapshots/ruleset.ipt"
        )
    ]

    links = []

    create_topology(devices, links, use_unix=True, interweave=False)
    if verbose: print "Topology sent to FaVe"

    if with_policy:
        if verbose: print "Initialize routes..."
        routes = [
            ('fw0', 1, 65535, [], ["fd=fw0.eth0"], []),
            ('fw0', 1, 0, ["ipv6_dst=2001:db8::2"], ["fd=fw0.eth1"], []),
        ]

        add_routes(routes, use_unix=use_unix)
        if verbose: print "Routes sent to FaVe"

        if verbose: print "Initialize sources..."
        sources = [(
            "source.Internet",
            "generator",
            [
                "ipv6_src=0::0/0"
            ]
        ), (
            "source.web",
            "generator",
            [
                "ipv6_src=2001:db8::2"
            ]
        )]

        links = [
            ('source.Internet.1', 'fw0.eth0', True),
            ('source.web.1', 'fw0.eth1', True)
        ]

        add_sources(sources, links, use_unix=use_unix)
        if verbose: print "Sources sent to FaVe"

        if verbose: print "Initialize probes..."
        probes = [(
            "probe.Internet",
            "probe",
            "universal",
            None,
            None,
            None,
            None
        ), (
            "probe.web",
            "probe",
            "universal",
            None,
            None,
            None,
            None
        )]

        links = [
            ('fw0.eth0', 'probe.Internet.1', False),
            ('fw0.eth1', 'probe.web.1', False)
        ]

        add_policies(probes, links, use_unix=use_unix)
        if verbose: print "Probes sent to FaVe"

    time.sleep(1)

    sleep_interval = 1.0 / no_req
    total_req = duration * no_req
    if verbose: print "Send %d states with a rate of %d req/s (interval: %.04fs)..." % (total_req, no_req, sleep_interval)
    fave = connect_to_fave(FAVE_DEFAULT_UNIX) if use_unix else connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
    requests = [
        _generate_request('fw0', i) for i in range(total_req)
    ]
    fave_sendmsg(fave, requests[0])

    for no, req in enumerate(requests[1:], start=1):
        fave.close()
        fave = connect_to_fave(FAVE_DEFAULT_UNIX) if use_unix else connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
        time.sleep(sleep_interval)
        fave_sendmsg(fave, req)
    fave.close()
    if verbose: print "States sent to FaVe"

    if verbose: print "Wait for fave..."
    import netplumber.dump_np as dumper
    dumper.main([] + (["-u" if use_unix else []]))

    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))
    t_start = time.time()
    os.system("python2 misc/await_fave.py")
    t_end = time.time()

    os.system("rm -f np_dump/.lock")
    if verbose: print "Benchmark finished... ",
    print "waited for %.4f seconds" % (t_end - t_start)
