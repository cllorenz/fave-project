#!/usr/bin/env python2

""" This module benchmarks FaVe with an example workload.
"""

import os
import sys
import logging
import time
import json

import netplumber.dump_np as dumper
import test.check_flows as checker

from bench.bench_utils import create_topology, add_rulesets, add_routes, add_sources, add_policies

LOGGER = logging.getLogger("example")
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.DEBUG)

TMPDIR = "/tmp/np"
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

INVENTORY = "bench/wl_example/inventory.json"
TOPOLOGY = "bench/wl_example/topology.json"
ROUTES = "bench/wl_example/routes.json"
SOURCES="bench/wl_example/sources.json"
POLICIES = "bench/wl_example/policies.json"
CHECKS = "bench/wl_example/checks.json"

REACH_CSV = "bench/wl_example/reachability.csv"
REACH_JSON = "bench/wl_example/reachable.json"


if __name__ == "__main__":
    LOGGER.info("generate policy matrix...")
    os.system(
        "python2 ../policy-translator/policy_translator.py " + ' '.join([
            "--csv", "--out", REACH_CSV,
            "bench/wl_example/roles_and_services.txt",
            "bench/wl_example/reach.txt"
        ])
    )
    LOGGER.info("generated policy matrix.")

    LOGGER.info("generate inventory...")
    os.system("python2 bench/wl_example/inventorygen.py")
    LOGGER.info("generated inventory.")

    LOGGER.info("convert policy matrix to checks...")
    os.system(
        "python2 bench/wl_example/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH_CSV,
            '-m', INVENTORY,
            '-c', CHECKS,
            '-j', REACH_JSON
        ])
    )
    LOGGER.info("converted policy matrix.")

    LOGGER.info("generate topology, routes, and probes...")
    os.system("python2 bench/wl_example/topogen.py")
    os.system("python2 bench/wl_example/routegen.py")
    os.system("python2 bench/wl_example/policygen.py")
    LOGGER.info("generated topology, routes, and probes.")

    LOGGER.info("starting netplumber...")
    os.system("scripts/start_np.sh bench/wl_example/np.conf")
    LOGGER.info("started netplumber.")

    LOGGER.info("starting aggregator...")
    os.system("scripts/start_aggr.sh")
    LOGGER.info("started aggregator.")

    LOGGER.info("initialize topology...")
    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        LOGGER.info("  create topology")
        create_topology(devices, links)
        LOGGER.info("  add rulesets")
        add_rulesets(devices)
    LOGGER.info("initialized topology.")


    LOGGER.info("initialize routes...")
    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        add_routes(routes)
    LOGGER.info("initialized routes...")

    LOGGER.info("initialize sources...")
    with open(SOURCES, 'r') as raw_sources:
        sources, links = json.loads(raw_sources.read()).values()
        add_sources(sources, links)
    LOGGER.info("initialized sources")

    LOGGER.info("initialize probes...")
    with open(POLICIES, 'r') as raw_policies:
        links, probes = json.loads(raw_policies.read()).values()

        add_policies(probes, links)
    LOGGER.info("initialized probes...")

    with open(CHECKS, 'r') as raw_checks:
        checks = json.loads(raw_checks.read())

    LOGGER.info("dumping fave and netplumber...")
    dumper.main(["-atnp"])
    LOGGER.info("dumped fave and netplumber.")

    LOGGER.info("stopping fave and netplumber...")
    os.system("bash scripts/stop_fave.sh")
    LOGGER.info("stopped fave and netplumber.")

    LOGGER.info("checking flow trees...")
    checker.main(["-r", "-c", ";".join(checks)])
    LOGGER.info("checked flow trees.")

    os.system("rm -f np_dump/.lock")