#!/usr/bin/env python3

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


""" This module generates the example workload's topology.
"""

import json
import sys

TOPOLOGY = "bench/wl_tum/topology.json"
SOURCES = "bench/wl_tum/sources.json"

def _main(argv):
    address = "2001:db8::1"
    ruleset = "bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset"
    if len(argv) == 3:
        address = "2001:db8::1" if argv[1] == "ipv6" else "10.0.0.1"
        ruleset = argv[2]

    devices = [
        ("fw.tum", "packet_filter", ['eth0', 'eth1'], address, ruleset)
    ]

    links = []

    sources = [
        ("source.tum", "generator", [
            "tcp_src=10000;tcp_dst=80"
        ])
    ]

    source_links = [
        ("source.tum.1", "fw.tum.forward_filter_in", True)
    ]

    topology = {
        'devices' : devices,
        'links' : links
    }

    sources = {
        'devices' : sources,
        'links' : source_links
    }

    json.dump(topology, open(TOPOLOGY, 'w'), indent=2)
    json.dump(sources, open(SOURCES, 'w'), indent=2)

if __name__ == '__main__':
    _main(sys.argv)
