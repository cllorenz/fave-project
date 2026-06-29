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

""" From-zero performance comparison: FaVe+APKeep vs FaVe+NetPlumber
(APKEEP_BACKEND.md, P5 / §6).

Measures the user-perceived, from-zero response time -- full model build +
compliance analysis, started fresh (not incremental) -- for each verification
backend, driven through the *identical* in-process path (InProcessFaVe over an
AggregatorService) so the number reflects the engine, not the packaging. Both
backends run as native libraries in-process (libapkeep via JPype, libnetplumber
via pybind11); there is no RPC, file shim or live net_plumber.

JVM warm-up confound (§6): a .so-loaded NetPlumber has ~zero startup, a JVM pays
boot + class-load + JIT. So we keep the JVM resident, run N from-zero builds,
and report the steady-state (median of post-warm-up runs) AND the cold single
shot, separately and labelled. The compliance workload is the full all-pairs
source->probe reachability matrix (cond-free), identical for both backends.

Usage:  PYTHONPATH=. python3 bench/apkeep_vs_netplumber.py [iterations] [warmup]
Manual/nightly only (needs the APKeep jar + libnetplumber .so built).
"""

import os
import statistics
import subprocess
import sys

from time import perf_counter

_PREFIX = "bench/wl_ifi"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("topology.json", "routes.json", "sources.json", "policies.json")]


def _logger():
    import logging
    log = logging.getLogger("apkeep_vs_netplumber")
    log.setLevel(logging.ERROR)
    return log


def _names(engine):
    from apkeep.adapter import APKeepAdapter
    if isinstance(engine, APKeepAdapter):
        return sorted(engine._generators), sorted(engine._probes)
    return sorted(engine.generators), sorted(engine.probes)


def _from_zero_run(make_engine):
    """ One from-zero run: construct the engine, build the whole wl_ifi model,
    and run the full reachability compliance -- timed end to end. """
    from util.in_process_driver import InProcessFaVe
    start = perf_counter()
    engine = make_engine()
    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        sources, probes = _names(engine)
        rules = {p: [[s, False, []] for s in sources] for p in probes}
        fave.check_compliance(rules)
    return perf_counter() - start


def _benchmark(label, make_engine, iterations, warmup):
    times = []
    for i in range(iterations):
        times.append(_from_zero_run(make_engine))
    cold = times[0]
    steady = times[warmup:] or times
    print("%-12s cold=%7.1f ms   steady(median)=%7.1f ms   min=%7.1f ms   "
          "(n=%d, warmup=%d)" % (
              label, cold * 1e3, statistics.median(steady) * 1e3,
              min(times) * 1e3, iterations, warmup))
    return {"label": label, "cold_ms": cold * 1e3,
            "steady_median_ms": statistics.median(steady) * 1e3,
            "min_ms": min(times) * 1e3, "all_ms": [t * 1e3 for t in times]}


def main(argv):
    iterations = int(argv[0]) if len(argv) > 0 else 12
    warmup = int(argv[1]) if len(argv) > 1 else 3

    if not all(os.path.isfile(f) for f in _INPUTS):
        print("wl_ifi inputs missing; generating ...")
        subprocess.check_call(["bash", "test/gen_wl_ifi_inputs.sh"])

    from apkeep.adapter import APKeepAdapter, available as apkeep_available
    from netplumber import lib_adapter

    if not apkeep_available():
        print("APKeep unavailable (JPype/jar); skipping.")
        return 0
    if lib_adapter.libnetplumber is None:
        print("libnetplumber not built; skipping.")
        return 0
    from netplumber.lib_adapter import NetPlumberLibAdapter

    log = _logger()
    print("from-zero comparison on wl_ifi (model build + full reachability), "
          "in-process, %d iterations:\n" % iterations)
    # NetPlumber first (no warm-up); then APKeep (first run pays JVM boot+JIT).
    _benchmark("NetPlumber", lambda: NetPlumberLibAdapter(log), iterations, warmup)
    _benchmark("APKeep", lambda: APKeepAdapter(log), iterations, warmup)
    print("\nNote: APKeep 'cold' includes JVM boot + JIT (one-time per process); "
          "'steady' is the warm-JVM from-zero. NetPlumber has no warm-up.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
