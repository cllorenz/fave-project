#!/usr/bin/env python2

""" This module benchmarks FaVe using an example workload.
"""

from util.bench_utils import create_topology, add_rulesets, add_routes, add_policies, add_sources


MAP = "bench/wl_tum/map.json"
TOPOLOGY = "bench/wl_tum/topology.json"
ROUTES = "bench/wl_tum/routes.json"
SOURCES="bench/wl_tum/sources.json"
POLICIES = "bench/wl_tum/policies.json"
CHECKS = "bench/wl_tum/checks.json"
REACH_JSON = "bench/wl_tum/reachable.json"

REACH = "bench/wl_tum/reachability.csv"

RULESET = 'bench/wl_tum/rulesets/tum-ruleset'

if __name__ == '__main__':
    import json
    import os
    import sys
    import getopt

    verbose = False
    ip = 'ipv4'
    ruleset = RULESET
    mapping = 'bench/wl_tum/mapping.json'

    use_unix = True

    try:
        opts, args = getopt.getopt(sys.argv[1:], "vm:r:46")
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
        if opt == '-m':
            mapping = arg

    if verbose: print "Generate benchmark..."

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    if ruleset == 'bench/wl_tum/rulesets/pgf.uni-potsdam.de-ruleset':
        os.system("bash scripts/generate-pgf-ruleset.sh bench/wl_tum")
        os.system("sed -i 's/ -i / -i eth/g' %s" % ruleset)
        os.system("sed -i 's/ -o / -o eth/g' %s" % ruleset)

    os.system("python2 bench/wl_tum/topogen.py %s %s" % (ip, ruleset))
    os.system("python2 bench/wl_tum/routegen.py")

    os.system("python2 bench/wl_tum/policygen.py")

    if verbose:
        print "Run benchmark..."

    arguments = "-l bench/wl_tum/np.conf"
    if mapping:
        arguments += " -L %s" % (json.load(open(mapping, 'r'))['length'] / 8)

    if use_unix:
        arguments += " -u /dev/shm/np1.socket"
    else:
        arugments += " -s 127.0.0.1 -p 44001"

    os.system(
        "bash scripts/start_np.sh %s" % arguments
    )

    arguments = ""
    if mapping:
        arguments += " -m %s" % mapping

    if use_unix:
        arguments += " -u -S %s" % "/dev/shm/np1.socket"
    else:
        arguments += " -S 127.0.0.1:44001"

    os.system(
        "bash scripts/start_aggr.sh " + arguments
    )

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        if verbose: print "Initialize topology..."
        create_topology(devices, links, use_unix=use_unix)
        if verbose: print "Topology sent to FaVe"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        if verbose: print "Initialize routes..."
        add_routes(routes, use_unix=use_unix)
        if verbose: print "Routes sent to FaVe"

    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        if verbose: print "Initialize probes..."
        add_policies(probes, links, use_unix=use_unix)
        if verbose: print "Probes sent to FaVe"

    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.loads(raw_sources.read()).values()

        if verbose: print "Initialize sources..."
        add_sources(sources, links, use_unix=use_unix)
        if verbose: print "Sources sent to FaVe"

    import netplumber.dump_np as dumper
    dumper.main(["-ant%s" % ("u" if use_unix else "")])

    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))

    if verbose: print "Wait for FaVe..."
    os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
