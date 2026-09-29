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

""" Which workloads the Delta-net distribution provides, and from what.

**The registry is the anti-drift device.** D6 moved the derivation up a tier so
that a second workload would not copy it; a registry is what makes the promise
checkable, because adding a workload is then a line HERE plus a driver, and
`test.sh` and the input generator both loop over this dict rather than over a
hand-maintained list that can fall behind it.

Keyed by directory name under `bench/`, valued by the vendored trace in
`bench/deltanet/traces/`. The name says which TRACE the workload models, not
which network: both Airtel traces are AS 9498 under two failure regimes, and
`README.md` states that where a directory name cannot.
"""

from typing import Dict


#: workload directory -> vendored trace.
WORKLOADS: Dict[str, str] = {
    'wl_airtel1': 'airtel1-only-inserts.csv',
    'wl_airtel2': 'airtel2-only-inserts.csv',
}

#: workload directory -> DERIVED trace (`traces/DERIVED.SHA256SUMS`).
#:
#: **Deliberately not in `WORKLOADS`**, and that is the whole difference. The
#: trace is gitignored and re-derived from the kept archive, so a checkout
#: without the archive -- CI's -- has no input for these; and `wl_berkeley`'s
#: generation takes ~7 minutes and ~16 GB (CLOUD_BENCH_PLAN.md §2.15). A dict
#: that `test.sh` and `gen_deltanet_inputs.sh` loop over is the wrong place for
#: either. They are built by name (`build('wl_berkeley')`, `bash
#: test/gen_deltanet_inputs.sh wl_berkeley`) and by nothing else.
DERIVED: Dict[str, str] = {
    'wl_berkeley': 'berkeley-inserts.csv',
}


def trace_of(name: str) -> str:
    """ The trace a workload models, from either dict. """
    if name in WORKLOADS:
        return WORKLOADS[name]
    if name in DERIVED:
        return DERIVED[name]
    raise KeyError(
        "%r is not a Delta-net workload -- registered: %s; derived: %s. A "
        "workload that is not in WORKLOADS is invisible to test.sh and to the "
        "input generator's default, which is the point: they loop over it."
        % (name, ', '.join(sorted(WORKLOADS)), ', '.join(sorted(DERIVED))))


def prefix_of(name: str) -> str:
    """ The `bench/`-relative prefix a workload's artifacts live under. """
    trace_of(name)
    return 'bench/%s' % name
