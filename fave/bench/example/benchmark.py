#!/usr/bin/env python2

""" This module benchmarks FaVe using an example workload.
"""

from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies

IFI = {
    "topology" : [],
    "hosts" : [],
    "routers" : [],
    "vlans" : [],
    "routes" : []
}

MAP = "bench/example/map.json"
TOPOLOGY = "bench/example/topology.json"
ROUTES = "bench/example/routes.json"
POLICIES = "bench/example/policies.json"
CHECKS = "bench/example/checks.json"
REACH_JSON = "bench/example/reachable.json"

REACH = "bench/example/reachability.csv"


if __name__ == '__main__':
    import json
    import os
    import sys

    verbose = False
    if len(sys.argv) > 1:
        verbose = sys.argv[1] == '-v'

    if verbose: print "Generate benchmark... ",

    os.system("rm -f /tmp/np/*")

    os.system("python2 bench/example/topogen.py")
    os.system("python2 bench/example/routegen.py")
    os.system(
        "python2 ../policy-translator/policy_translator.py " +
        "--strict " +
        "--csv --out %s " % REACH +
        "bench/example/inventory.txt " +
        "bench/example/policy.txt"
    )
    os.system(
        "python2 bench/example/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH,
            '-m', MAP,
            '-c', CHECKS,
            '-j', REACH_JSON
        ])
    )

    os.system("python2 bench/example/policygen.py")

    if verbose:
        print "ok"
        print "Run benchmark... ",

    os.system("bash scripts/start_np.sh bench/example/np.conf")
    os.system("bash scripts/start_aggr.sh")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        create_topology(devices, links)
        add_rulesets(devices)

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        add_routes(routes)

    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        add_policies(probes, links)

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    import netplumber.dump_np as dumper
    dumper.main(["-anpft"])

    os.system("bash scripts/stop_fave.sh")

    if verbose:
        print "ok"
        print "Check results... ",

    import test.check_flows as checker
    checker.main(["-b", "-r", "-c", ";".join(checks)])

    os.system("rm -f np_dump/.lock")
