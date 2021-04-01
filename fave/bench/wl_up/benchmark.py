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

LOGGER = logging.getLogger("up")
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.DEBUG)

#TMPDIR = "/tmp/np"
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

    LOGGER.info("starting netplumber...")
    for no in range(1,tds+1):
        sockopt = "-u /dev/shm/np%s.socket" % no if use_unix else "-s 127.0.0.1 -p 44%03d" % no
        os.system("bash scripts/start_np.sh -l bench/wl_up/np.conf %s" % sockopt)
    LOGGER.info("started netplumber.")

    LOGGER.info("starting aggregator...")
    os.system(
        "bash scripts/start_aggr.sh -S %s %s" % (
            ','.join([
                ("/dev/shm/np%d.socket" if use_unix else "127.0.0.1:44%03d") % no for no in range(1, tds+1)
            ]),
            "-u" if use_unix else ""
        )
    )
    LOGGER.info("started aggregator.")

    LOGGER.info("initialize topology...")
    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        LOGGER.info("  create topology")
        create_topology(devices, links, use_unix=use_unix)
        LOGGER.info("  add rulesets")
        add_rulesets(devices, use_unix=use_unix)
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
    dumper.main(["-ant%s" % ("u" if use_unix else "")])
    LOGGER.info("ordered fave to dump")

    LOGGER.info("stopping fave and netplumber...")
    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))
    LOGGER.info("ordered fave to stop")

    LOGGER.info("wait for fave to check flow trees...")
    os.system("python2 misc/await_fave.py")
    os.system("bash scripts/check_parallel.sh %s %s" % (CHECKS, tds))
    LOGGER.info("checked flow trees.")

    os.system("rm -f np_dump/.lock")
