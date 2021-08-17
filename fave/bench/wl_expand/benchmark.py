#!/usr/bin/env python2

""" This module benchmarks FaVe by filling a switch table and then enforce a header space expansion.
"""

import random
import json
import os
import argparse
import sys

from util.model_util import TABLE_MAX
from util.aggregator_utils import connect_to_fave, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX, fave_sendmsg
from devices.switch import SwitchCommand
from rule.rule_model import Rule, Match, RuleField, Forward
from bench.bench_utils import create_topology

def _random_port():
    return random.randint(0, 65535)

def _random_ipv6_address():
    return ':'.join(["{:04x}".format(random.randint(0, 65535)) for _i in range(8)])

def _random_ipv6_prefix():
    return _random_ipv6_address() + '/' + str(random.randint(0,128))

def _generate_rule(node, i):
    return Rule(
        node,
        node+'.1',
        i,
        in_ports=[node+'.'+str(random.randint(1, 24))],
        match=Match([
            RuleField('packet.ipv6.destination', _random_ipv6_prefix()),
            RuleField('packet.ipv6.proto', random.choice(['udp', 'tcp'])),
            RuleField('packet.upper.dport', _random_port())
        ]),
        actions=[Forward(ports=[node+'.'+str(random.randint(1, 24))])]
    )

def _generate_large_rule(node, i):
    rule = _generate_rule(node, i)
    rule.match.extend([
        RuleField('packet.ipv6.source', _random_ipv6_prefix()),
        RuleField('packet.upper.sport', _random_port())
    ])
    return rule

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c', '--count', 
        type=int, dest="count", default=10, 
        help="the rule count that is inserted before the expansion (default: 10)"
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

    count = args.count
    verbose = args.verbose
    use_unix = not args.use_tcp

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    os.system("bash scripts/start_np.sh -l bench/wl_expand/np.conf %s" % (
        "-u /dev/shm/np1.socket" if use_unix else "-s 127.0.0.1 -p 44001")
    )
    os.system("bash scripts/start_aggr.sh -S %s %s" % (
        "/dev/shm/np1.socket" if use_unix else "127.0.0.1:44001",
        "-u" if use_unix else ""
    ))

    if verbose: print "Initialize topology..."
    devices = [
        (
            "sw0",
            "switch",
            24,
            None
        )
    ]

    links = []

    create_topology(devices, links, use_unix=True, interweave=False)
    if verbose: print "Topology sent to FaVe"


    pre_rules1 = [
        _generate_rule('sw0', i) for i in range(count-10)
    ]

    pre_rules2 = [
        _generate_rule('sw0', i) for i in range(count-10, count)
    ]

    post_rules = [
        _generate_large_rule('sw0', count)
    ]

    fave = connect_to_fave(FAVE_DEFAULT_UNIX) if use_unix else connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
    fave_sendmsg(fave, json.dumps(SwitchCommand('sw0', 'add_rules', pre_rules1).to_json()))
    fave.close()

    fave = connect_to_fave(FAVE_DEFAULT_UNIX) if use_unix else connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
    fave_sendmsg(fave, json.dumps(SwitchCommand('sw0', 'add_rules', pre_rules2).to_json()))
    fave.close()

    fave = connect_to_fave(FAVE_DEFAULT_UNIX) if use_unix else connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
    fave_sendmsg(fave, json.dumps(SwitchCommand('sw0', 'add_rules', post_rules).to_json()))
    fave.close()

    if verbose: print "Rules %d sent to FaVe" % (count + 1)

    if verbose: print "Wait for FaVe..."
    import netplumber.dump_np as dumper
    dumper.main(["-u"] if use_unix else [])

    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))
    os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
    if verbose: print "Benchmark finished"
