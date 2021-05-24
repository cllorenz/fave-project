#!/usr/bin/env python2

import os
import json

from netplumber.mapping import Mapping
from bench.np_preparation import prepare_benchmark
from bench.bench_utils import create_topology, add_routes
from bench.bench_helpers import array_ipv4_to_cidr, array_vlan_to_number, array_to_int

ROLES='bench/wl_i2/roles.txt'
POLICY='bench/wl_i2/reach.txt'
REACH='bench/wl_i2/reach.csv'

CHECKS='bench/wl_i2/checks.json'

TOPOLOGY='bench/wl_i2/i2-json/device_topology.json'
ROUTES='bench/wl_i2/i2-json/routes.json'
SOURCES='bench/wl_i2/i2-json/sources.json'
PROBES='bench/wl_i2/i2-json/probes.json'

MAP_FILE='bench/wl_i2/i2-json/mapping.json'
with open(MAP_FILE, 'r') as mf:
    MAPPING = Mapping.from_json(json.loads(mf.read()))


# run benchmark
if __name__ == '__main__':
    intervals = {
        (0, 1) : 0,         # x00000 -> ingress table out port
        (1, 10000) : 0,     # x0000y -> ingress table in port
        (10000, 10001) : 1, # x20000 -> egress table in port
        (20001, 30000) : 1  # x2000y -> egress table out port
    }

    prepare_benchmark(
        "bench/wl_i2/i2-json",
        TOPOLOGY,
        SOURCES,
        PROBES,
        ROUTES,
        MAPPING,
        intervals
    )

    use_unix = True

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    os.system(
        "python2 ../policy-translator/policy_translator.py " + ' '.join([
            "--csv", "--out", REACH, ROLES, POLICY
        ])
    )

    os.system(
        "python2 bench/wl_i2/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH, '-c', CHECKS
        ])
    )

    os.system(
        "bash scripts/start_np.sh -L 6 -l bench/wl_i2/np.conf %s" % (
            "-u /dev/shm/np1.socket" if use_unix  else "-s 127.0.0.1 -p 44001"
        )
    )
    os.system(
            "bash scripts/start_aggr.sh -m %s -S %s %s" % (
            (MAP_FILE, "/dev/shm/np1.socket", "-u") if use_unix else (MAP_FILE, "127.0.0.1:44001", "")
        )
    )

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.load(raw_topology).values()

        print "create topology..."
        create_topology(devices, links, use_unix=use_unix)
        print "topology sent to fave"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.load(raw_routes)

        print "add routes..."
        add_routes(routes, use_unix=use_unix)
        print "routes sent to fave"

    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.load(raw_sources).values()

        print "create sources..."
        create_topology(sources, links, use_unix=use_unix)
        print "sources sent to fave"

    with open(PROBES, 'r') as raw_probes:
        probes, links = json.load(raw_probes).values()

        print "create probes..."
        create_topology(probes, links, use_unix=use_unix)
        print "probes sent to fave"

    print "wait for fave..."

    import netplumber.dump_np as dumper
    dumper.main(["-ans%s" % ("u" if use_unix else "")])

    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))

    import test.check_flows as checker
    checks = json.load(open(CHECKS, 'r'))
    checker.main(["-b", "-c", ";".join(checks)])

    os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
