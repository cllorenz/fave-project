#!/usr/bin/env python2

""" This module provides utility functionality to build benchmarks for FaVe and
    NetPlumber.
"""

import json
import os

import netplumber.dump_np as dumper
import test.check_flows as checker

from topology import topology as topo
from ip6np import ip6np as ip6tables
from openflow import switch


def _add_packet_filter(name, _type, ports, address, _ruleset):
    topo.main([
        "-a",
        "-t", "packet_filter",
        "-n", name,
        "-i", address,
        "-p", str(ports)
    ])


def _add_switch(name, _type, ports):
    topo.main(["-a", "-t", "switch", "-n", name, "-p", str(ports)])


def _add_router(name, _type, ports, acls):
    topo.main(["-a", "-t", "router", "-n", name, "-p", str(ports), "-r", acls])


def _add_generator(name, _type, fields=None):
    opts = []
    if fields:
        opts.extend(["-f", ';'.join(fields)])

    topo.main(["-a", "-t", "generator", "-n", name] + opts)


def _add_probe(name, _type, quantor, filter_fields=None, test_fields=None, test_path=None):
    opts = []
    if filter_fields:
        opts.extend(["-F", ';'.join(filter_fields)])
    if test_fields:
        opts.extend(["-T", ';'.join(test_fields)])
    if test_path:
        opts.extend(["-P", ';'.join(test_path)])

    topo.main(["-a", "-t", "probe", "-n", name, "-q", quantor] + opts)


def _add_link(src, dst):
    topo.main(["-a", "-l", "%s:%s" % (src, dst)])


def _add_rule(name, table=None, idx=None, fields=None, commands=None, in_ports=None):
    opts = []
    if table:
        opts.extend(["-t", str(table)])
    if idx:
        opts.extend(["-i", str(idx)])
    if fields:
        opts.extend(["-f", ';'.join(fields)])
    if commands:
        opts.extend(["-c", ','.join(commands)])
    if in_ports:
        opts.extend(["-p", ','.join([str(p) for p in in_ports])])

    switch.main(["-a", "-n", name] + opts)


def _add_ruleset(name, _type, ports, address, ruleset):
    ip6tables.main(["-n", name, "-p", ports, "-i", address, "-f", ruleset])


_DEVICES = {
    "packet_filter" : _add_packet_filter,
    "switch" : _add_switch,
    "router" : _add_router,
    "generator" : _add_generator,
    "probe" : _add_probe,
    "host" : _add_packet_filter
}

def create_topology(devices, links):
    """ Builds a topology from devices and links.

    Keyword arguments:
    devices - a set of devices
    links - a set of links between the devices
    """

    get_type = lambda x: x[1]

    for device in devices:
        dtype = get_type(device)
        try:
            _DEVICES[dtype](*device)
        except KeyError as e:
            raise Exception("No such device type: %s" % e.message)

    for link in links:
        _add_link(*link)


def add_routes(routes):
    """ Add routing rules.

    Keyword arguments:
    routes - a set of routing rules
    """
    for route in routes:
        _add_rule(*route)


def add_rulesets(devices):
    """ Add rulesets to a set of devices.

    Keyword arguments:
    devices - a set of devices
    """

    get_type = lambda x: x[1]
    for device in [d for d in devices if get_type(d) in ["packet_filter", "host"]]:
        _add_ruleset(*device)


def add_policies(probes, links):
    """ Add probe nodes to the topology.

    Keyword arguments:
    probes - a set of probe nodes
    links - a set of links
    """

    get_type = lambda x: x[1]
    for probe in [p for p in probes if get_type(p) == 'probe']:
        _add_probe(*probe)

    for link in links:
        _add_link(*link)
