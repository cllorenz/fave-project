#!/usr/bin/env python2

from topology import router
from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies

IFI={
    "topology" : [],
    "hosts" : [],
    "routers" : [],
    "vlans" : [],
    "routes" : []
}

TOPOLOGY="bench/wl-ifi/topology.json"
ROUTES="bench/wl-ifi/routes.json"
POLICIES="bench/wl-ifi/policies.json"
CHECKS="bench/wl-ifi/checks.json"


def campus_network(config):
    topology, hosts, routers, vlans, routes = config.viewvalues()

    for router in routers:
        pass


if __name__ == '__main__':
    import json
    import os

    os.system("python2 bench/wl-ifi/topogen.py")
    os.system("python2 bench/wl-ifi/routegen.py")
    os.system("python2 bench/wl-ifi/policygen.py")
    os.system("python2 bench/wl-ifi/checkgen.py")

    os.system("bash scripts/start_np.sh bench/wl-ifi/np.conf")
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
