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

""" Benchmarks FaVe on the Berkeley insert block (CLOUD_BENCH_PLAN.md §2.15).

`berkeley-inserts.csv` is the insert block of the Delta-net archive's
`berkeley.csv`: 12,817,902 rules over 584,944 prefixes and 23 routers, the
trace's peak state (§2.14). It is DERIVED, not vendored -- gitignored, pinned
in `traces/DERIVED.SHA256SUMS`, re-derived by `archive_survey/insert_block.sh`
-- so it is not in the registry's `WORKLOADS`, and neither `test.sh` nor the
input generator's default builds it.

**A real prefix set on a synthetic forwarding structure** (§2.15): the prefixes
look like an Internet RIB, the forwarding is "straight to the egress" over a
complete graph less one link. Its value is size and LPM volume. What is
invented and stamped -- ports, the drop rule, the unread fourth field, a matrix
from a walk -- is in `bench/deltanet/workload.py`, `RouterTraceBenchmark`.
"""

import logging
import sys

from bench.deltanet.workload import build


#: This directory's name, and its key in `bench/deltanet/registry.py`'s DERIVED.
NAME = 'wl_berkeley'


def main():
    logging.basicConfig(level=logging.INFO)
    build(NAME).run()


if __name__ == '__main__':
    sys.exit(main())
