#!/usr/bin/env python2

""" This module benchmarks FaVe with the UP workload.
"""

import os
import sys
import logging
import time
import json

import netplumber.dump_np as dumper
import test.check_flows as checker

from bench.bench_utils import create_topology, add_rulesets, add_routes, add_sources, add_policies

from util import parallel_utils

LOGGER = logging.getLogger("up")
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.DEBUG)

TMPDIR = "/dev/shm/np"
os.system("mkdir -p %s" % TMPDIR)

LOGGER.info("deleting old logs and measurements...")
os.system("rm -f %s/*.log" % TMPDIR)
LOGGER.info("deleted old logs and measurements.")

logging.basicConfig(
    format='%(asctime)s [%(name)s.%(levelname)s] - %(message)s',
    level=logging.INFO,
    filename="%s/fave.log" % TMPDIR,
    filemode='w'
)

INVENTORY = "bench/wl_up/inventory.json"
TOPOLOGY = "bench/wl_up/topology.json"
ROUTES = "bench/wl_up/routes.json"
SOURCES="bench/wl_up/sources.json"
POLICIES = "bench/wl_up/policies.json"
CHECKS = "bench/wl_up/checks.json"

REACH_CSV = "bench/wl_up/reachability.csv"
REACH_JSON = "bench/wl_up/reachable.json"


if __name__ == "__main__":
    use_unix = True
    use_tcp_np = False
    use_interweaving = True

    verbose = True # XXX

    tds = 1
    if len(sys.argv) == 2:
        tds = int(sys.argv[1])

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    LOGGER.info("generate policy matrix...")
    os.system(
        "python2 ../policy-translator/policy_translator.py " + ' '.join([
            "--strict",
            "--csv", "--out", REACH_CSV,
            "bench/wl_up/roles_and_services.txt",
            "bench/wl_up/reach.txt"
        ])
    )
    LOGGER.info("generated policy matrix.")

    LOGGER.info("generate rulesets...")
    os.system("bash scripts/generate-pgf-ruleset.sh bench/wl_up")
    os.system("bash scripts/generate-host-rulesets.sh bench/wl_up")
    os.system("bash scripts/generate-clients-rulesets.sh bench/wl_up")
    LOGGER.info("generated rulesets.")

    LOGGER.info("generate inventory...")
    os.system("python2 bench/wl_up/inventorygen.py")
    LOGGER.info("generated inventory.")

    LOGGER.info("convert policy matrix to checks...")
    os.system(
        "python2 bench/wl_up/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH_CSV,
            '-m', INVENTORY,
            '-c', CHECKS,
            '-j', REACH_JSON
        ])
    )
    LOGGER.info("converted policy matrix.")

    LOGGER.info("generate topology, routes, and probes...")
    os.system("python2 bench/wl_up/topogen.py")
    os.system("python2 bench/wl_up/routegen.py")
    os.system("python2 bench/wl_up/policygen.py")
    LOGGER.info("generated topology, routes, and probes.")

    import socket
    
    
    serverlist = []
    
    try:
        # get hosts from slurm environment variables
        serverlist = parallel_utils.get_serverlist()
        print('using slurm nodelist as serverlist')
    except Exception as e:
        # slurm environment variables not defined or parsing failed
        # build default serverlist
        print(repr(e))
        print('no slurm nodelist found, using default serverlist')
        hostname = socket.gethostname()
        print(hostname)
        host_ip = socket.gethostbyname(hostname)
        print(host_ip)
        
        cur_port = int(os.environ.get('start_port', 44001))

        tds = 1
        if len(sys.argv) == 2:
            try:
                tds = int(sys.argv[1])
            except Exception as e:
                print(repr(e))

        for no in range(0,tds):
            if use_tcp_np:
                serverlist.append({'host': host_ip, 'port': str(cur_port + no)})
            else:
                serverlist.append('/dev/shm/np%d.socket' % no)
        
        for server in serverlist:
            if use_tcp_np:
                sockopt = "-s %s -p %s" % (server['host'], server['port'])
            else:
                sockopt = "-u %s" % server
            print("bash scripts/start_np.sh -l bench/wl_up/np.conf %s" % sockopt)
            os.system("bash scripts/start_np.sh -l bench/wl_up/np.conf %s" % sockopt)

    print(serverlist)

    if use_tcp_np:
        aggr_args = [("%s:%s" % (server['host'], server['port'])) for server in serverlist]
    else:
        aggr_args = serverlist
    print("bash scripts/start_aggr.sh -a -S %s -u" % ','.join(aggr_args))
    os.system(
        "bash scripts/start_aggr.sh -a -S %s -u" % ','.join(aggr_args)
    )

    LOGGER.info("initialize topology...")
    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        create_topology(devices, links, use_unix=use_unix, interweave=use_interweaving)
    LOGGER.info("topology sent to fave")


    LOGGER.info("initialize routes...")
    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        add_routes(routes, use_unix=use_unix)
    LOGGER.info("routes sent to fave")

    LOGGER.info("initialize probes...")
    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        add_policies(probes, links, use_unix=use_unix)
    LOGGER.info("probes sent to fave")

    LOGGER.info("initialize sources...")
    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.loads(raw_sources.read()).values()
        add_sources(sources, links, use_unix=use_unix)
    LOGGER.info("sources sent to fave")

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    LOGGER.info("dumping fave and netplumber...")
    dumper.main(["-o", os.environ.get('np_flows_output_directory', 'np_dump'), "-a", "-n", "-t"] + (['-u'] if use_unix else []))
    LOGGER.info("ordered fave to dump")

    LOGGER.info("stopping fave and netplumber...")
    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))
    LOGGER.info("ordered fave to stop")

    LOGGER.info("wait for fave to check flow trees...")
    os.system("python2 misc/await_fave.py")
    os.system("bash scripts/check_parallel.sh %s %s %s" % (CHECKS, tds, "np_dump"))

# XXX: from golombek
#    import test.check_flows as checker
#    checker.main(["-b", "-r", "-c", ";".join(checks), '-d', os.environ['np_flows_output_directory']])
    LOGGER.info("checked flow trees.")

    os.system("rm -f np_dump/.lock")
