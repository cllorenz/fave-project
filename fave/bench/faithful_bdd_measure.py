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

""" Uncapped BDD-APKeep faithful (dst x VLAN) measurement driver
    (APKEEP_NDD_PLAN.md -> "Planned: uncapped BDD-APKeep faithful measurements").

Builds a *faithful* VLAN model (`faithful_vlan=True`) on the **BDD** engine and
records the definitive outcome the capped 28-min runs could not: the final
`ap_num`, the build + query wall time, the peak JVM heap, and the reachable-pair
count -- OR, if the JVM dies, the point at which it hit a heap ceiling.

Two modes, matching the plan:
  * FULL model (no --routers): the definitive uncapped run. Launch it detached,
    no `timeout`, biggest heap the box allows (FAVE_JVM_XMX), profiler on
    (APKEEP_BUILD_PROFILE / _MS). On a small-RAM box this is expected to *crawl*
    (the build is wall-clock bound -- superlinear PPM cost -- not heap bound; at
    the 28-min cap heap was ~0.41 GB of 11 GB), so it may not finish; the point
    is to extend the trajectory well past the cap and see whether ap_num ever
    plateaus or the JVM ever OOMs.
  * REDUCED slice (--routers a,b,c): the plan's hedge -- a subset small enough
    that the BDD build actually *completes*, giving a real final ap_num/time to
    anchor an extrapolation. Stanford router subsetting reuses the induced-
    subnetwork logic from `apkeep_convergence._filter_model`.

Build vs query are timed separately: the BDD/AP build is `_build()`, triggered
lazily by the first `single_universe()`/`check_compliance()` (NOT by `replay`),
so we force it with `single_universe()` and time that; the query is
`check_compliance` over the full source x probe matrix.

Usage (from fave/, PYTHONPATH=., venv active, apkeep jar built):
  # reduced slice (completes) -- the anchor:
  FAVE_JVM_XMX=11g PYTHONPATH=. python3 bench/faithful_bdd_measure.py \
      --bench stanford --routers bbra_rtr,rozb_rtr --out /path/result.json
  # full uncapped (detached, profiled, no timeout):
  FAVE_JVM_XMX=13g APKEEP_BUILD_PROFILE=<dir>/full_profile.jsonl \
      APKEEP_BUILD_PROFILE_MS=30000 PYTHONPATH=. \
      python3 bench/faithful_bdd_measure.py --bench stanford \
      --out <dir>/full_result.json
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time


_STANFORD_PREFIX = "bench/wl_stanford/stanford-json"
_STANFORD_FILES = {
    "topology": "device_topology.json",
    "routes": "routes.json",
    "policies": "probes.json",
    "sources": "sources.json",
}
_I2_PREFIX = "bench/wl_i2/i2-json"
_I2_FILES = {"topology": "device_topology.json", "policies": "probes.json"}


def _peak_heap_bytes():
    """ Peak heap across all JVM heap memory pools (getPeakUsage), which -- unlike
    a point-in-time getHeapMemoryUsage -- survives GC, so it is the real high-water
    mark of the build. Returns -1 if the JVM/JPype is unavailable. """
    try:
        import jpype
        if not jpype.isJVMStarted():
            return -1
        mf = jpype.JClass("java.lang.management.ManagementFactory")
        peak = 0
        for pool in mf.getMemoryPoolMXBeans():
            if str(pool.getType()) != "Heap memory":
                continue
            usage = pool.getPeakUsage()
            if usage is not None:
                peak = max(peak, int(usage.getUsed()))
        return peak
    except Exception:  # pragma: no cover - diagnostics only
        return -1


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _prepare_replay_dir(bench, routers):
    """ Return (replay_dir, files, cleanup). For a reduced Stanford slice, build an
    induced subnetwork in a temp dir; otherwise replay the committed model dir. """
    if bench == "stanford":
        if not routers:
            return _STANFORD_PREFIX, _STANFORD_FILES, None
        import bench.apkeep_convergence as conv
        model = conv._filter_model(conv._load_model(), set(routers))
        tmp = tempfile.mkdtemp(prefix="faithful_bdd_")
        conv._write_model(model, tmp)
        return tmp, _STANFORD_FILES, tmp
    if bench == "i2":
        if routers:
            raise SystemExit("i2 router subsetting is not implemented yet")
        return _I2_PREFIX, _I2_FILES, None
    raise SystemExit("unknown bench %r" % bench)


def measure(bench, routers, out_path):
    from apkeep.adapter import APKeepAdapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("faithful_bdd"); log.setLevel(logging.WARNING)
    replay_dir, files, cleanup = _prepare_replay_dir(bench, routers)

    eng = APKeepAdapter(log, faithful_vlan=True, engine='bdd')
    wall0 = time.time()
    result = {
        "bench": bench,
        "engine": "bdd",
        "faithful_vlan": True,
        "routers": sorted(routers) if routers else None,
        "xmx": os.environ.get("FAVE_JVM_XMX"),
        "profile": os.environ.get("APKEEP_BUILD_PROFILE"),
    }
    try:
        with InProcessFaVe(eng) as fave:
            fave.replay(replay_dir, files=files)
            sources = sorted(eng._generators)
            probes = sorted(eng._probes)
            result["sources"] = len(sources)
            result["probes"] = len(probes)

            t0 = time.time()
            eng.single_universe()             # forces _build() -> the BDD/AP build
            result["build_s"] = round(time.time() - t0, 3)
            result["ap_num"] = int(eng._lib.ap_num())
            result["element_metrics"] = dict(eng._lib.element_metrics())
            result["peak_heap_mb"] = round(_peak_heap_bytes() / 2**20, 1)

            rules = {p: [[s, False, []] for s in sources] for p in probes}
            tq = time.time()
            fave.check_compliance(rules)
            result["query_s"] = round(time.time() - tq, 3)

        not_reach = {(s, p) for (s, p, _m, _c) in eng.get_compliance_results()}
        reach = {(s, p) for p in probes for s in sources if (s, p) not in not_reach}
        reach_nonself = {(s, p) for (s, p) in reach if _base(s) != _base(p)}
        result["reachable_pairs"] = len(reach)
        result["reachable_pairs_nonself"] = len(reach_nonself)
        result["peak_heap_mb"] = round(_peak_heap_bytes() / 2**20, 1)
        result["status"] = "completed"
    finally:
        result["wall_s"] = round(time.time() - wall0, 3)
        if cleanup:
            import shutil
            shutil.rmtree(cleanup, ignore_errors=True)

    print(json.dumps(result, indent=2))
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=2)
        print("wrote %s" % out_path, file=sys.stderr)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bench", choices=("stanford", "i2"), required=True)
    p.add_argument("--routers", help="comma-separated router bases -> reduced "
                                     "induced slice (stanford only)")
    p.add_argument("--out", help="write the result JSON here")
    args = p.parse_args(argv)
    routers = [r for r in args.routers.split(",") if r] if args.routers else None
    measure(args.bench, routers, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
