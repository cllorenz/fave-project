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

TOPOLOGY = "bench/wl_ifi/topology.json"
ROUTES = "bench/wl_ifi/routes.json"
POLICIES = "bench/wl_ifi/policies.json"
CHECKS = "bench/wl_ifi/checks.json"


def campus_network(config):
    topology, hosts, routers, vlans, routes = config.viewvalues()

    for router in routers:
        pass


if __name__ == '__main__':
    import json
    import os

    os.system("python2 bench/wl_ifi/topogen.py")
    os.system("python2 bench/wl_ifi/routegen.py")
    os.system("python2 bench/wl_ifi/policygen.py")
    #os.system("python2 bench/wl_ifi/checkgen.py")
    os.system(
        "python2 ../policy-translator/policy_translator.py " +
        "--csv --out bench/wl_ifi/reachability.csv " +
        "bench/wl_ifi/roles_and_services.orig.txt " +
        "bench/wl_ifi/policy.orig.txt"
    )
    os.system(
        "python2 bench/wl_ifi/reach_csv_to_checks.py " +
        "-p bench/wl_ifi/reachability.csv " +
        "-m bench/wl_ifi/vlan_to_dn.json " +
        "-c %s" % CHECKS
    )

    os.system("bash scripts/start_np.sh bench/wl_ifi/np.conf")
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
    import test.check_flows as checker

    dumper.main(["-anpft"])
    checker.main(["-c", ";".join(checks)])

    os.system("bash scripts/stop_fave.sh")
    os.system("rm -f np_dump/.lock")
