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

MAP = "bench/wl_tum/map.json"
TOPOLOGY = "bench/wl_tum/topology.json"
ROUTES = "bench/wl_tum/routes.json"
POLICIES = "bench/wl_tum/policies.json"
CHECKS = "bench/wl_tum/checks.json"
REACH_JSON = "bench/wl_tum/reachable.json"

REACH = "bench/wl_tum/reachability.csv"


if __name__ == '__main__':
    import json
    import os
    import sys

    verbose = False
    if len(sys.argv) > 1:
        verbose = sys.argv[1] == '-v'

    if verbose: print "Generate benchmark... ",

    os.system("rm -f /tmp/np/*")

    os.system("python2 bench/wl_tum/topogen.py")
    os.system("python2 bench/wl_tum/routegen.py")
#    os.system(
#        "python2 ../policy-translator/policy_translator.py " +
#        "--strict " +
#        "--csv --out %s " % REACH +
#        "bench/wl_tum/inventory.txt " +
#        "bench/wl_tum/policy.txt"
#    )
#    os.system(
#        "python2 bench/wl_tum/reach_csv_to_checks.py " + ' '.join([
#            '-p', REACH,
#            '-m', MAP,
#            '-c', CHECKS,
#            '-j', REACH_JSON
#        ])
#    )

    os.system("python2 bench/wl_tum/policygen.py")

    if verbose:
        print "ok"
        print "Run benchmark... ",

    os.system("bash scripts/start_np.sh bench/wl_tum/np.conf")
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

    #with open(CHECKS, 'r') as raw_checks:
    #    checks = json.loads(raw_checks.read())

    import netplumber.dump_np as dumper
    dumper.main(["-ant"])

    os.system("bash scripts/stop_fave.sh")

    if verbose:
        print "ok"
        print "Check results... ",

    #import test.check_flows as checker
    #checker.main(["-b", "-r", "-c", ";".join(checks)])
    os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
