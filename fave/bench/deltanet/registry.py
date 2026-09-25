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


#: workload directory -> vendored trace. `wl_airtel2` lands with D7.
WORKLOADS: Dict[str, str] = {
    'wl_airtel1': 'airtel1-only-inserts.csv',
}


def prefix_of(name: str) -> str:
    """ The `bench/`-relative prefix a workload's artifacts live under. """
    if name not in WORKLOADS:
        raise KeyError(
            "%r is not a Delta-net workload -- registered: %s. A workload that "
            "is not here is invisible to test.sh and to the input generator, "
            "which is the point: they loop over this dict."
            % (name, ', '.join(sorted(WORKLOADS))))
    return 'bench/%s' % name
