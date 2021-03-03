#!/usr/bin/env python2

""" This module benchmarks FaVe using the IFI workload.
"""

from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies

IFI = {
    "topology" : [],
    "hosts" : [],
    "routers" : [],
    "vlans" : [],
    "routes" : []
}

INVENTORY = "bench/wl_ifi/inventory.json"
TOPOLOGY = "bench/wl_ifi/topology.json"
ROUTES = "bench/wl_ifi/routes.json"
POLICIES = "bench/wl_ifi/policies.json"
CHECKS = "bench/wl_ifi/checks.json"
REACH_JSON = "bench/wl_ifi/reachable.json"

REACH = "bench/wl_ifi/reachability.csv"


if __name__ == '__main__':
    import json
    import os
    from os import path
    import sys

    verbose = False
    if len(sys.argv) > 1:
        verbose = sys.argv[1] == '-v'

    if verbose: print "Generate benchmark... "

    os.system("rm -f /tmp/np/*")

    os.system("python2 bench/wl_ifi/cisco_to_inventory.py")
    os.system("python2 bench/wl_ifi/inventorygen.py")
    os.system("python2 bench/wl_ifi/topogen.py")
    os.system("python2 bench/wl_ifi/routegen.py")
    #os.system("python2 bench/wl_ifi/checkgen.py")
    if not path.exists(REACH):
        os.system(
            "python2 ../policy-translator/policy_translator.py " +
            "--csv --out %s " % REACH +
            "bench/wl_ifi/roles_and_services.orig.txt " +
            "bench/wl_ifi/policy.orig.txt"
        )
    os.system(
        "python2 bench/wl_ifi/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH,
            '-m', INVENTORY,
            '-c', CHECKS,
            '-j', REACH_JSON
        ])
    )

    os.system("python2 bench/wl_ifi/policygen.py")

    if verbose:
        print "Run benchmark... "

    os.system("bash scripts/start_np.sh bench/wl_ifi/np.conf np1")
    os.system("bash scripts/start_aggr.sh np1")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        if verbose: print "Initialize Topology"
        create_topology(devices, links)
        add_rulesets(devices)
        if verbose: print "Topology sent to FaVe"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        if verbose: print "Initialize routes..."
        add_routes(routes)
        if verbose: print "Routes sent to FaVe"

    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        if verbose: print "Initialize probes..."
        add_policies(probes, links)
        if verbose: print "Probes sent to FaVe"

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    if verbose: print "Wait for FaVe"

    import netplumber.dump_np as dumper
    dumper.main(["-anpft"])

    os.system("bash scripts/stop_fave.sh")

    if verbose:
        print "Check results... "

    import test.check_flows as checker
    checker.main(["-b", "-r", "-c", ";".join(checks)])

    os.system("rm -f np_dump/.lock")
