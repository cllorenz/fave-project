#!/usr/bin/env python2

""" This module benchmarks FaVe using an generic workload.
"""

from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies, add_sources


TOPOLOGY = "bench/wl_generic_fw/topology.json"
ROUTES = "bench/wl_generic_fw/routes.json"
SOURCES="bench/wl_generic_fw/sources.json"
POLICIES = "bench/wl_generic_fw/policies.json"
CHECKS = "bench/wl_generic_fw/checks.json"
ROLES = "bench/wl_generic_fw/roles.json"
REACH_JSON = "bench/wl_generic_fw/reachable.json"

REACH = "bench/wl_generic_fw/reachability.csv"


if __name__ == '__main__':
    import json
    import os
    import sys
    import getopt

    verbose = False
    ip = 'ipv6'
    ruleset = "bench/wl_generic_fw/default/ruleset"
    policy = "bench/wl_generic_fw/default/policy.txt"
    inventory = "bench/wl_generic_fw/default/inventory.txt"

    try:
        opts, args = getopt.getopt(sys.argv[1:], "vr:p:i:46")
    except getopt.GetoptError as err:
        print "unknown arguments"
        print err
        sys.exit(1)

    for opt, arg in opts:
        if opt == '-v':
            verbose = True
        if opt == '-r':
            ruleset = arg
        if opt == '-p':
            policy = arg
        if opt == '-i':
            inventory = arg
        if opt == '-4':
            ip = 'ipv4'
        if opt == '-6':
            ip = 'ipv6'

    if verbose: print "Generate benchmark... ",

    os.system("rm -f /tmp/np/*")

    os.system(
        "python2 ../policy-translator/policy_translator.py " +
        "--strict " +
        "--csv --out %s " % REACH +
        "--roles %s " % ROLES +
        "%s " % inventory +
        policy
    )

    os.system("python2 bench/wl_generic_fw/topogen.py %s %s" % (ip, ruleset))
    os.system("python2 bench/wl_generic_fw/routegen.py")

    os.system(
        "python2 bench/wl_generic_fw/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH,
            '-c', CHECKS,
            '-j', REACH_JSON
        ])
    )

    os.system("python2 bench/wl_generic_fw/policygen.py")

    if verbose:
        print "ok"
        print "Run benchmark... ",

    os.system("bash scripts/start_np.sh bench/wl_generic_fw/np.conf")
    os.system("bash scripts/start_aggr.sh")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        create_topology(devices, links)
        add_rulesets(devices)

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        add_routes(routes)

    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.loads(raw_sources.read()).values()

        add_sources(sources, links)

    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        add_policies(probes, links)

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    import netplumber.dump_np as dumper
    dumper.main(["-anpt"])

    os.system("bash scripts/stop_fave.sh")

    if verbose:
        print "ok"
        print "Check results... ",

    import test.check_flows as checker
    checker.main(["-b", "-r", "-c", ";".join(checks)])
    #os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
