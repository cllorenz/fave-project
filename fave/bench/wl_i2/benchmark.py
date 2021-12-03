#!/usr/bin/env python2

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

""" This module benchmarks FaVe using the Internet2 workload.
"""

import os
import json
import logging

from netplumber.mapping import Mapping
from bench.np_preparation import prepare_benchmark
from bench.generic_benchmark import GenericBenchmark


class Internet2Benchmark(GenericBenchmark):
    """ This class provides the Internet2 benchmark.
    """

    def _pre_preparation(self):
        intervals = {
            (0, 1) : 0,         # x00000 -> ingress table out port
            (1, 10000) : 0,     # x0000y -> ingress table in port
            (10000, 10001) : 1, # x20000 -> egress table in port
            (20001, 30000) : 1  # x2000y -> egress table out port
        }

        with open(self.files['i2_mapping'], 'r') as mf:
            mapping = Mapping.from_json(json.loads(mf.read()))

        prepare_benchmark(
            "%s/i2-json" % self.prefix,
            self.files['topology'],
            self.files['sources'],
            self.files['i2_probes'],
            self.files['routes'],
            mapping,
            intervals
        )


if __name__ == '__main__':
    files = {
        "topology" : "bench/wl_i2/i2-json/device_topology.json",
        "routes" : "bench/wl_i2/i2-json/routes.json",
        "sources" : "bench/wl_i2/i2-json/sources.json",
        "policies" : "bench/wl_i2/i2-json/probes.json",
        "i2_probes" : "bench/wl_i2/i2-json/probes.json",
        'roles_services' : 'bench/wl_i2/roles.txt',
        'reach_csv' : 'bench/wl_i2/reach.csv',
        'i2_mapping' : 'bench/wl_i2/i2-json/mapping.json'
    }

    length = json.load(open(files['i2_mapping'], 'r'))['length'] / 8

    Internet2Benchmark(
        "bench/wl_i2",
        logger=logging.getLogger('i2'),
        extra_files=files,
        use_internet=False,
        length=length
    ).run()
