#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" Does NetPlumber's table-granular loop rule truncate anything? (TODO item 33)

NetPlumber stops a flow whose path revisits a table, whatever its header
(RuleNode::process_src_flow), and fires its loop callback exactly there. So the
count of loop reports on a workload is exact: ZERO proves the rule changed no
verdict on it. A nonzero count names the workloads whose truncations need a
look -- each may be a true loop, or a packet legitimately passing a table
twice (a router on a stick), which the rule loses.

Usage, from fave/ with PYTHONPATH=. and the venv active, after the workloads'
test/gen_*_inputs.sh and net_plumber/python/build_libnetplumber.sh:

    python3 bench/analysis/netplumber_loop_census.py
"""

import logging
import os
import sys
import time

_F = {"topology": "device_topology.json", "policies": "probes.json"}

WORKLOADS = [
    ("wl_airtel1", "bench/wl_airtel1", None),
    ("wl_airtel2", "bench/wl_airtel2", None),
    ("wl_i2", "bench/wl_i2/i2-json", _F),
    ("wl_stanford", "bench/wl_stanford/stanford-json", _F),
    ("wl_cloud", "bench/wl_cloud", None),
    ("wl_ifi", "bench/wl_ifi", None),
    ("wl_up", "bench/wl_up", None),
    ("wl_tum", "bench/wl_tum", None),
    ("wl_example", "bench/wl_example", None),
]


def loop_reports(prefix, files=None):
    from bench.feature_survey import raise_thread_errors
    from netplumber.lib_adapter import NetPlumberLibAdapter
    from util.in_process_driver import InProcessFaVe
    engine = NetPlumberLibAdapter(logging.getLogger("netplumber_loop_census"))
    with raise_thread_errors():
        with InProcessFaVe(engine) as fave:
            fave.replay(prefix, files=files)
    return engine.loop_reports()


def main(argv):
    only = set(argv) if argv else None
    for name, prefix, files in WORKLOADS:
        if only and name not in only:
            continue
        if not os.path.isfile(os.path.join(prefix, "routes.json")):
            print("%-12s skipped: inputs not generated" % name)
            continue
        t0 = time.time()
        n = loop_reports(prefix, files)
        print("%-12s loop reports %8d   (%.1fs)" % (name, n, time.time() - t0), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
