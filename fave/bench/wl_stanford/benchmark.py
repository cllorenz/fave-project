#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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

""" This module benchmarks FaVe using the Stanford workload.
"""

import os
import json
import logging

from netplumber.mapping import Mapping
from bench.np_preparation import prepare_benchmark
from bench.generic_benchmark import GenericBenchmark


class StanfordBenchmark(GenericBenchmark):
    """ This class provides the Stanford benchmark.
    """

    def _pre_preparation(self):
        intervals = {
            (0, 1) : 0,         # x00000 -> ingress table out port
            (1, 10000) : 0,     # x0000y -> ingress table in port
            (20000, 20001) : 1, # x20000 -> mid table in port
            (10001, 20000) : 1, # x1000y -> mid table out port
            (20001, 30000) : 2, # x2000y -> egress table out port
            (30001, 40000) : 2  # x3000y -> egress table in port
        }

        with open(self.files['stanford_mapping'], 'r') as mf:
            mapping = Mapping.from_json(json.loads(mf.read()))

        prepare_benchmark(
            "%s/stanford-json" % self.prefix,
            self.files['topology'],
            self.files['sources'],
            self.files['stanford_probes'],
            self.files['routes'],
            mapping,
            intervals
        )


if __name__ == '__main__':

    files = {
        "topology" : "bench/wl_stanford/stanford-json/device_topology.json",
        "routes" : "bench/wl_stanford/stanford-json/routes.json",
        "sources" : "bench/wl_stanford/stanford-json/sources.json",
        "policies" : "bench/wl_stanford/stanford-json/probes.json",
        "stanford_probes" : "bench/wl_stanford/stanford-json/probes.json",
        'roles_services' : 'bench/wl_stanford/roles.txt',
        'reach_csv' : 'bench/wl_stanford/reach.csv',
        'stanford_mapping' : 'bench/wl_stanford/stanford-json/mapping.json',
        'inventory' : 'bench/empty.json'
    }

    length = json.load(open(files['stanford_mapping'], 'r'))['length'] / 8

    StanfordBenchmark(
        "bench/wl_stanford",
        logger=logging.getLogger('stanford'),
        extra_files=files,
        use_internet=False,
        length=length
    ).run()
