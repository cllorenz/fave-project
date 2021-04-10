#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" This module provides utility functionality to build benchmarks for FaVe and
    NetPlumber.
"""

import json
import os
import time

import netplumber.dump_np as dumper
import test.check_flows as checker

from topology import topology as topo
from ip6np import ip6np as ip6tables
from openflow import switch


def _add_packet_filter(name, _type, ports, address, ruleset, use_unix=False):
    topo.main([
        "-a",
        "-t", "packet_filter",
        "-n", name,
        "-i", address,
        "-p", str(ports),
        "-r", ruleset
    ] + (['-u'] if use_unix else []))


def _add_switch(name, _type, ports, use_unix=False):
    topo.main(["-a", "-t", "switch", "-n", name, "-p", str(ports)] + (["-u"] if use_unix else []))


def _add_router(name, _type, ports, acls, use_unix=False):
    topo.main(["-a", "-t", "router", "-n", name, "-p", ','.join([str(p) for p in range(1, ports+1)]), "-r", acls] + (["-u"] if use_unix else []))


def _add_generator(name, _type, fields=None, use_unix=False):
    opts = ["-u"] if use_unix else []
    if fields:
        opts.extend(["-f", ';'.join(fields)])

    topo.main(["-a", "-t", "generator", "-n", name] + opts)


def _add_generators(generators, use_unix=False):
    topo.main(["-a", "-t", "generators", "-G", '|'.join(["%s\\%s" % (n, ';'.join(f)) for n, _t, f in generators])] + (["-u"] if use_unix else []))


def _add_probe(name, _type, quantor, match=None, filter_fields=None, test_fields=None, test_path=None, use_unix=False):
    opts = ["-u"] if use_unix else []
    if match:
        opts.extend(["-f", ';'.join(match)])
    if filter_fields:
        opts.extend(["-F", ';'.join(filter_fields)])
    if test_fields:
        opts.extend(["-T", ';'.join(test_fields)])
    if test_path:
        opts.extend(["-P", ';'.join(test_path)])

    topo.main(["-a", "-t", "probe", "-n", name, "-q", quantor] + opts)


def _add_link(src, dst, use_unix=False):
    topo.main(["-a", "-l", "%s:%s" % (src, dst)] + (["-u"] if use_unix else []))

def _add_links(links, use_unix=False):
    topo.main(["-a", "-l", ",".join(["%s:%s:%s" % (src, dst, bulk) for src, dst, bulk in links])] + (["-u"] if use_unix else []))

def _add_rule(name, table=None, idx=None, fields=None, commands=None, in_ports=None, use_unix=False):
    opts = ["-U"] if use_unix else []
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


def _add_ruleset(name, _type, ports, address, ruleset, use_unix=False):
    ip6tables.main(["-n", name, "-p", ports, "-i", address, "-f", ruleset] + (["-u"] if use_unix else []))


_DEVICES = {
    "packet_filter" : _add_packet_filter,
    "switch" : _add_switch,
    "router" : _add_router,
    "generator" : _add_generator,
    "probe" : _add_probe,
    "host" : _add_packet_filter
}

def create_topology(devices, links, use_unix=False):
    """ Builds a topology from devices and links.

    Keyword arguments:
    devices - a set of devices
    links - a set of links between the devices
    """

    get_type = lambda x: x[1]

    for device in devices:
        dtype = get_type(device)
        try:
            t_start = time.time()
            _DEVICES[dtype](*device, use_unix=use_unix)
            t_end = time.time()
            print "parse device %s: %s ms" % (dtype, (t_end - t_start) * 1000.0)
        except KeyError as e:
            raise #Exception("No such device type: %s" % e.message)

    if links:
        _add_links(links, use_unix=use_unix)


def add_routes(routes, use_unix=False):
    """ Add routing rules.

    Keyword arguments:
    routes - a set of routing rules
    """
    for route in routes:
        _add_rule(*route, use_unix=use_unix)


def add_rulesets(devices, use_unix=False):
    """ Add rulesets to a set of devices.

    Keyword arguments:
    devices - a set of devices
    """

    get_type = lambda x: x[1]
    for device in [d for d in devices if get_type(d) in ["packet_filter", "host"]]:
        _add_ruleset(*device, use_unix=use_unix)


def add_policies(probes, links, use_unix=False):
    """ Add probe nodes to the topology.

    Keyword arguments:
    probes - a set of probe nodes
    links - a set of links
    """

    get_type = lambda x: x[1]
    for probe in [p for p in probes if get_type(p) == 'probe']:
        _add_probe(*probe, use_unix=use_unix)

    if links:
        _add_links(links, use_unix=use_unix)


def add_sources(sources, links, use_unix=False):
    """ Add source nodes to the topology.

    Keyword arguments:
    probes - a set of probe nodes
    links - a set of links
    """

    get_type = lambda x: x[1]
    _add_generators([s for s in sources if get_type(s) == 'generator'], use_unix=use_unix)

    if links:
        _add_links(links, use_unix=use_unix)
