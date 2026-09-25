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

""" Benchmarks FaVe on the Airtel 2 snapshot (CLOUD_BENCH_PLAN.md §2, D7).

The same network as `wl_airtel1` under a different failure regime: Airtel 1
fails a single inter-switch link at a time and recovers it before the next,
Airtel 2 induces all 2-pair link failures including their recovery (§2.3). So
the topology, the 1,400 prefixes and the homing are identical, and **3,300
`(router, prefix)` keys forward somewhere different** -- 155 directed port-edges
against airtel1's 158.

**This is a robustness check, not a differential** (§2.3, and D7 states it
again because it is the thing most likely to drift). The reachability matrix is
derived from the homing, the homing is identical, so the expectation is the same
by construction -- `test_both_traces_state_the_same_matrix` asserts exactly
that, and §2.5's finer per-prefix measurement is 21,000/21,000 on both traces.
What is being tested is whether three engine TRANSLATIONS agree on a second,
genuinely different forwarding state; the answer is known before any of them
starts.

Everything else lives in `bench/deltanet/workload.py`, which is the point of
D6: this file is the trace's name and nothing else.
"""

import logging
import sys

from bench.deltanet.workload import build


#: This directory's name, and its key in `bench/deltanet/registry.py`.
NAME = 'wl_airtel2'


def main():
    logging.basicConfig(level=logging.INFO)
    build(NAME).run()


if __name__ == '__main__':
    sys.exit(main())
