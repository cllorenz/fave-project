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

""" The Delta-net dataset FAMILY: everything shared by the workloads built from
it (CLOUD_BENCH_PLAN.md 2.2, D6).

This is tier 2 of three. `bench/` above it is cross-workload; `bench/wl_*/`
below it is one model, one policy, one set of generated artifacts. What lives
HERE is what more than one of those workloads needs and none of them owns:

  * `trace.py`       -- the NSDI'17 CSV format, and D1's priority identity
  * `topology.py`    -- the switch/port graph the `s<i>-<j>` names encode
  * `preparation.py` -- the FaVe device model
  * `policy.py`      -- the FPL inventory and reachability matrix
  * `census.py`      -- `TRACES.md`, generated
  * `traces/`        -- the vendored CSVs and their `SHA256SUMS`

**The raw data is why this tier has to exist at all.** One `SHA256SUMS` covers
both traces and every workload reads it; duplicating the directory per workload
would duplicate the pin, and a guard that exists twice is a guard that can
disagree with itself (`util/raw_data.py`).

**`deltanet` names the DISTRIBUTION, not a network.** The archive holds eleven
CSVs spanning `inet`, `rf3257`, `rf6461` and `berkley-ribs-*` besides the two
Airtel ones, which is why the workloads are named after their traces and this
package is not. See `README.md` for what the Airtel pair actually is.
"""
