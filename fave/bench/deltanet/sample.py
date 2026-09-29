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

""" A smaller snapshot of the same trace, for measuring how cost scales
(CLOUD_BENCH_PLAN.md §2.15).

`wl_berkeley` is 13.4M rules, and the FaVe pipeline's memory per rule puts the
full model out of reach of a 19 GB machine for every engine (measured there).
So it is measured as a SERIES: the same trace at 1/k of its prefixes, for a
few k, with the cost read off as a function of size.

**Which prefixes, and why not a uniform sample.** Every k-th prefix in address
order -- all of its rules, so a kept prefix is forwarded exactly as in the full
trace -- PLUS every prefix that makes LPM observable: each prefix with an
ancestor homed at a different router, and all of its ancestors. Those are what
produce the matrix cells only longest-prefix fallback reaches (§2.15), and a
uniform 1% would drop nearly all of them, so a small sample would answer a
different, LPM-blind matrix and its cost would not be comparable with the
full one's. With them kept, every size can answer the same matrix -- which is
checked per run, not assumed: the stamp carries the walk's result.

`keep_every=1` is the whole trace, and returns it unchanged.
"""

from __future__ import annotations

from typing import Dict, List, Set

from bench.deltanet.fib_walk import regions
from bench.deltanet.trace import Insert


def lpm_witnesses(homed: Dict[str, int]) -> Set[str]:
    """ Every prefix with an ancestor homed elsewhere, and its ancestors. """
    keep: Set[str] = set()
    for chain in regions(homed):
        specific = chain[0]
        if any(homed[a] != homed[specific] for a in chain[1:]):
            keep.update(chain)
    # A prefix wholly covered by its children has no region of its own, but
    # still has ancestors; `regions` puts it in its children's chains, so it
    # is reached as an ancestor there if it matters.
    return keep


def sample(inserts: List[Insert], homed: Dict[str, int],
           keep_every: int) -> List[Insert]:
    """ The inserts of every `keep_every`-th prefix in address order, and of
    every LPM witness. """
    if keep_every < 1:
        raise ValueError("keep_every must be at least 1, not %d" % keep_every)
    if keep_every == 1:
        return inserts
    order = sorted(homed, key=_address_order)
    kept = set(order[::keep_every]) | lpm_witnesses(homed)
    return [insert for insert in inserts if insert.prefix in kept]


def _address_order(prefix: str):
    address, _, length = prefix.partition('/')
    return tuple(int(octet) for octet in address.split('.')) + (int(length),)
