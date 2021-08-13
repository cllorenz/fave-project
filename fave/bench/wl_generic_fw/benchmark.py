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


def _print_help():
    options = [
        "-4 - use ipv4 for the packet filter",
        "-6 - use ipv6 for the packet filter (default)",
        "-i <inventory> - an inventory file specified in FPL",
        "-p <policy> - a policy file specified in FPL",
        "-r <ruleset> - an iptables rule set",
        "-s - FPL policies should be handled in strict mode",
        "-m <map> - a mapping file with internal and external to interface mappings of the form { \"external\" : \"eth0\", \"internal\" : \"eth1\" }",
        "-v - verbose output"
    ]
    print "usage:\nPYTHONPATH=. python2 bench/wl_generic_fw/benchmark [OPTIONS]\nOptions:"
    for opt in options:
        print " ", opt


if __name__ == '__main__':
    import json
    import os
    import sys
    import getopt

    verbose = False
    ip = 'ipv6'
    strict = ''
    ruleset = "bench/wl_generic_fw/default/ruleset"
    policy = "bench/wl_generic_fw/default/policy.txt"
    inventory = "bench/wl_generic_fw/default/inventory.txt"
    interfaces = "bench/wl_generic_fw/default/interfaces.json"

    use_internet = True
    use_state_snapshots = False
    use_unix = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvsr:p:i:m:nu46")
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
        if opt == '-s':
            strict = '--strict '
        if opt == '-m':
            interfaces = arg
        if opt == '-n':
            use_internet = False
            use_state_snapshots = True
        if opt == '-h':
            _print_help()
            sys.exit(0)
        if opt == '-u':
            use_unix = True

    if verbose: print "Generate benchmark..."

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    os.system(
        "python2 ../policy-translator/policy_translator.py " +
        strict +
        ("--no-internet " if not use_internet else "") +
        "--csv --out %s " % REACH +
        "--roles %s " % ROLES +
        "%s " % inventory +
        policy
    )

    if verbose: print "Policy translated"

    os.system('cp %s bench/wl_generic_fw/interfaces.json' % interfaces)

    if verbose: print "Interface mapping copied"

    os.system("python2 bench/wl_generic_fw/topogen.py %s %s" % (ip, ruleset))
    os.system("python2 bench/wl_generic_fw/routegen.py")

    if verbose: print "Topology and routes generated"

    os.system(
        "python2 bench/wl_generic_fw/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH,
            '-c', CHECKS,
            '-j', REACH_JSON
        ])
    )

    if verbose: print "CSV converted to checks."

    os.system("python2 bench/wl_generic_fw/policygen.py")

    if verbose:
        print "Benchmark generated"
        print "Run benchmark... "

    os.system("bash scripts/start_np.sh -l bench/wl_generic_fw/np.conf %s" % (
        "-u /dev/shm/np1.socket" if use_unix else "-s 127.0.0.1 -p 44001")
    )
    os.system("bash scripts/start_aggr.sh -S %s %s" % (
        "/dev/shm/np1.socket" if use_unix else "127.0.0.1:44001",
        "-u" if use_unix else ""
    ))

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        if verbose: print "Initialize topology..."
        create_topology(devices, links, use_unix=use_unix, interweave=not use_state_snapshots)
        if verbose: print "Topology sent to FaVe"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        if verbose: print "Initialize routes..."
        add_routes(routes, use_unix=use_unix)
        if verbose: print "Routes sent to FaVe"

    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.loads(raw_sources.read()).values()

        if verbose: print "Initialize sources..."
        add_sources(sources, links, use_unix=use_unix)
        if verbose: print "Sources sent to FaVe"

    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        if verbose: print "Initialize probes..."
        add_policies(probes, links, use_unix=use_unix)
        if verbose: print "Probes sent to FaVe"

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    if verbose: print "Wait for fave..."

    import netplumber.dump_np as dumper
    dumper.main(["-a", "-n", "-t"] + (["-u"] if use_unix else []))

    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))

    if verbose:
        print "Check results..."

    import test.check_flows as checker
    checker.main(["-b", "-r", "-c", ";".join(checks)])
    #os.system("python2 misc/await_fave.py")

    os.system("rm -f np_dump/.lock")
