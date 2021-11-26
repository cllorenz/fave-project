#!/usr/bin/env python2

""" This module benchmarks FaVe using the IFI workload.
"""

import argparse

from util.bench_utils import create_topology, add_rulesets, add_routes, add_policies
from util import parallel_utils

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
    import socket

    use_unix = True
    use_tcp_np = False

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_const', dest='verbose', default=False, const=True)
    parser.add_argument('-t', '--threads', action='store', dest='threads', default=1, type=int)

    args = parser.parse_args(sys.argv[1:])

    verbose = args.verbose
    tds = args.threads


    if verbose: print "Generate benchmark... "

    os.system("rm -f /dev/shm/*.socket")
    os.system("rm -f /dev/shm/np/*")

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

    if verbose: print "Run benchmark... "

    if not use_tcp_np:
        # use unix sockets to communicate to NP backend
        for no in range(1,tds+1):
            sockopt = "-u /dev/shm/np%s.socket" % no
            os.system("bash scripts/start_np.sh -l bench/wl_ifi/np.conf %s" % sockopt)

        aggr_args = [
            "/dev/shm/np%d.socket" % no for no in range(1, tds+1)
        ]
        os.system(
            "bash scripts/start_aggr.sh -S %s %s" % (
                ','.join(aggr_args),
                "-u" if use_unix else ""
            )
        )

    else:
        serverlist = []

        try:
            # get hosts from slurm environment variables
            serverlist = parallel_utils.get_serverlist()
        except Exception as e:
            # slurm environment variables not defined or parsing failed
            # build default serverlist
            hostname = socket.gethostname()
            host_ip = socket.gethostbyname(hostname)

            cur_port = 44001

            for no in range(0,tds):
                serverlist.append({'host': host_ip, 'port': str(cur_port + no)})

            for server in serverlist:
                sockopt = "-s %s -p %s" % (server['host'], server['port'])
                os.system("bash scripts/start_np.sh -l bench/wl_ifi/np.conf %s" % sockopt)

        aggr_args = [("%s:%s" % (server['host'], server['port'])) for server in serverlist]
        os.system(
            "bash scripts/start_aggr.sh -S %s -u" % ','.join(aggr_args)
        )

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        if verbose: print "Initialize Topology"
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

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    if verbose: print "Wait for FaVe"

    import netplumber.dump_np as dumper
    dumper.main(["-o", os.environ.get('np_flows_output_directory', 'np_dump'), "-a", "-n", "-p", "-f", "-t"] + (['-u'] if use_unix else []))

    os.system("bash scripts/stop_fave.sh %s" % ('-u' if use_unix else ''))

    if verbose:
        print "Check results... "

    import test.check_flows as checker
    checker.main(["-b", "-r", "-c", ";".join(checks), '-d', os.environ.get('np_flows_output_directory', 'np_dump')])

    os.system("rm -f {}/.lock".format(os.environ.get('np_flows_output_directory', 'np_dump')))
