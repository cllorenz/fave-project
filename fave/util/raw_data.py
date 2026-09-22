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

""" Vendored raw data is checked against its manifest before anything reads it.

CLOUD_BENCH_PLAN.md §1.8, the owner's standing principle: every benchmark and
every measurement must be recreatable from the raw data, because manual edits
made while debugging are how wrong inputs get in and stay in.

This lives in `util/` rather than beside one workload because it now guards
two of them -- `bench/wl_cloud/cloud-tf/` and
`bench/wl_deltanet/deltanet-traces/` -- and a second copy of a guard is a guard
that can disagree with itself. `bench.wl_cloud.benchmark` re-exports both names
so its own callers did not have to move.
"""

from __future__ import annotations

import hashlib
import os

from typing import List


class RawDataError(Exception):
    """ The vendored raw data does not match its manifest. """


def verify_raw(raw_dir: str) -> None:
    """ Check every vendored file against `SHA256SUMS`.

    The whole workload is regenerated from this directory on every run, so a
    byte that changed here silently changes what the benchmark measures. Loud,
    and BEFORE anything is derived: a manual edit made while debugging is
    exactly how a benchmark comes to measure something nobody intended, and it
    is unrecoverable once the edit is forgotten.
    """
    manifest = os.path.join(raw_dir, 'SHA256SUMS')
    if not os.path.isfile(manifest):
        raise RawDataError("%s is missing: the raw data has no manifest to "
                           "check against" % manifest)

    bad: List[str] = []
    for line in open(manifest, 'r'):
        expected, name = line.split()
        path = os.path.join(raw_dir, name)
        if not os.path.isfile(path):
            bad.append("%s is missing" % name)
            continue
        digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        if digest != expected:
            bad.append("%s: expected %s, found %s" % (name, expected, digest))

    if bad:
        raise RawDataError(
            "the vendored raw data under %s does not match SHA256SUMS:\n  %s"
            % (raw_dir, "\n  ".join(bad)))
