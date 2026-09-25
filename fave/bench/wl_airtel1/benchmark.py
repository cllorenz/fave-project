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

""" Benchmarks FaVe on the Airtel 1 snapshot (CLOUD_BENCH_PLAN.md §2).

`airtel1-only-inserts.csv` is the trace the Delta-net paper publishes figures
for -- 38,100 rules, 158 links, 68 nodes, matched exactly by the derivation
(§2.3) -- and it is the only one any engine had run as of D6. What the model is,
what the property is and what the run should report are all in
`bench/deltanet/workload.py`, because none of it is specific to this trace.

**Airtel 1 and Airtel 2 are ONE network under two failure regimes**, not two
networks: single inter-switch link failures with recovery here, all 2-pair
failures there. `bench/deltanet/README.md` has the naming, which this directory
cannot state.
"""

import logging
import sys

from bench.deltanet.workload import build


#: This directory's name, and its key in `bench/deltanet/registry.py`.
NAME = 'wl_airtel1'


def main():
    logging.basicConfig(level=logging.INFO)
    build(NAME).run()


if __name__ == '__main__':
    sys.exit(main())
