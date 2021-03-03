#!/usr/bin/env python2

""" This module benchmarks FaVe using an example workload.
"""

from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies, add_sources


MAP = "bench/wl_tum/map.json"
TOPOLOGY = "bench/wl_tum/topology.json"
ROUTES = "bench/wl_tum/routes.json"
SOURCES="bench/wl_tum/sources.json"
POLICIES = "bench/wl_tum/policies.json"
CHECKS = "bench/wl_tum/checks.json"
REACH_JSON = "bench/wl_tum/reachable.json"

REACH = "bench/wl_tum/reachability.csv"

RULESET = 'bench/wl_tum/rulesets/pgf.uni-potsdam.de-ruleset'

if __name__ == '__main__':
    import json
    import os
    import sys
    import getopt

    verbose = False
    ip = 'ipv6'
    ruleset = RULESET

    try:
        opts, args = getopt.getopt(sys.argv[1:], "vr:46")
    except getopt.GetoptError as err:
        print err
        sys.exit(1)

    for opt, arg in opts:
        if opt == '-v':
            verbose = True
        if opt == '-r':
            ruleset = arg
        if opt == '-4':
            ip = 'ipv4'
        if opt == '-6':
            ip = 'ipv6'

    if verbose: print "Generate benchmark..."

    os.system("rm -f /tmp/np/*")

    os.system("bash scripts/generate-pgf-ruleset.sh bench/wl_tum")
    if ruleset == RULESET:
        os.system("sed -i 's/ -i / -i eth/g' %s" % ruleset)
        os.system("sed -i 's/ -o / -o eth/g' %s" % ruleset)

    os.system("python2 bench/wl_tum/topogen.py %s %s" % (ip, ruleset))
    os.system("python2 bench/wl_tum/routegen.py")

    os.system("python2 bench/wl_tum/policygen.py")

    if verbose:
        print "Run benchmark..."

    os.system("bash scripts/start_np.sh bench/wl_tum/np.conf np1")
    os.system("bash scripts/start_aggr.sh np1")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        if verbose: print "Initialize topology..."
        create_topology(devices, links)
        add_rulesets(devices)
        if verbose: print "Topology sent to FaVe"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        if verbose: print "Initialize routes..."
        add_routes(routes)
        if verbose: print "Routes sent to FaVe"

    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.loads(raw_sources.read()).values()

        if verbose: print "Initialize sources..."
        add_sources(sources, links)
        if verbose: print "Sources sent to FaVe"

    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        if verbose: print "Initialize probes..."
        add_policies(probes, links)
        if verbose: print "Probes sent to FaVe"

    import netplumber.dump_np as dumper
    dumper.main(["-ant"])

    os.system("bash scripts/stop_fave.sh")

    if verbose: print "Wait for FaVe..."
    os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
