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

""" VeriFlow-FR's calibration against Delta-net Table 4 (VERIFLOW_PLAN.md §8).

WHAT IS REPRODUCED. Delta-net §4.3.2 poses 158 "what if a link fails?"
queries on the 38,100-rule Airtel snapshot -- `wl_airtel1`'s trace
(bench/deltanet/TRACES.md) -- and reports an average query time of 4.5 ms for
its VeriFlow reimplementation, Veriflow-RI (0.04 ms for Delta-net), on a
3.47 GHz Xeon, single-threaded. This replays wl_airtel1, enumerates Delta-net's
graph (`veriflow.translate.node_edges`: 158 edges, the paper's query count),
and answers `veriflow_fr`'s `link_failure` per edge: the affected ECs and their
forwarding graphs, timed inside the engine.

WHAT IS NOT KNOWN, and asked (VERIFLOW_PLAN.md Q11-Q13): whether a query is
one directed edge, whether Veriflow-RI's figure includes a property check, and
what is inside its timed region. This measures graph construction only, per
edge, on a loaded snapshot.

THE STOPPING RULE, declared before measuring (CLOUD_BENCH_PLAN.md §3): one
cold pass, then five warm passes, all 158 edges in a fixed order each time.
The headline is the mean over the warm passes; every pass is reported.

THE GATE: the warm mean within an order of magnitude of 4.5 ms -- 0.45 to
45 ms -- with the hardware difference stated. It calibrates against
Veriflow-RI, which "may ... be faster than Veriflow" (DN §5).

Usage, from fave/ with PYTHONPATH=. and the venv active, after
test/gen_deltanet_inputs.sh and veriflow_fr/python/build_libveriflow_fr.sh:

    python3 bench/analysis/veriflow_calibration.py [--json out.json]
"""

import argparse
import json
import logging
import os
import platform
import statistics
import subprocess
import sys
import time

from typing import Any, Dict, List

PUBLISHED_MS = 4.5          # Veriflow-RI, DN Table 4, Airtel
PUBLISHED_QUERIES = 158
WARM_PASSES = 5


def _cpu() -> str:
    try:
        with open("/proc/cpuinfo") as raw:
            for line in raw:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git"] + list(args), capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def measure(prefix: str = "bench/wl_airtel1") -> Dict[str, Any]:
    from util.in_process_driver import InProcessFaVe
    from veriflow.adapter import VeriFlowAdapter
    from veriflow.translate import node_edges

    engine = VeriFlowAdapter(logging.getLogger("veriflow_calibration"))
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
    engine.build()
    ir = engine.ir
    assert ir is not None
    edges = node_edges(ir)
    if len(edges) != PUBLISHED_QUERIES:
        raise SystemExit("expected %d edges (DN §4.3.2), found %d"
                         % (PUBLISHED_QUERIES, len(edges)))

    passes: List[List[float]] = []
    ecs: List[int] = []
    graphs: List[int] = []
    for n in range(1 + WARM_PASSES):
        times = []
        for table, in_port, to_port in edges:
            n_ecs, n_graphs, secs = engine.net.link_failure(table, in_port, to_port)
            times.append(secs * 1000.0)
            if n == 0:
                ecs.append(n_ecs)
                graphs.append(n_graphs)
        passes.append(times)

    warm = [t for p in passes[1:] for t in p]
    warm_mean = statistics.mean(warm)
    with open(os.path.join(prefix, "SOURCE.json")) as raw:
        source = json.load(raw)
    return {
        "workload": prefix,
        "source": source,
        "queries": len(edges),
        "affected_ecs": {"total": sum(ecs), "mean": statistics.mean(ecs),
                         "max": max(ecs), "zero": ecs.count(0)},
        "graphs_built": {"total": sum(graphs), "mean": statistics.mean(graphs)},
        "cold_pass_mean_ms": statistics.mean(passes[0]),
        "warm_pass_means_ms": [statistics.mean(p) for p in passes[1:]],
        "warm_mean_ms": warm_mean,
        "warm_median_ms": statistics.median(warm),
        "warm_max_ms": max(warm),
        "published_ms": PUBLISHED_MS,
        "ratio_to_published": warm_mean / PUBLISHED_MS,
        "gate_within_10x": PUBLISHED_MS / 10 <= warm_mean <= PUBLISHED_MS * 10,
        "stamps": dict(ir.stamps, **{
            "cpu": _cpu(),
            "published_cpu": "3.47 GHz Xeon (DN §4)",
            "threads": 1,
            "compiler": subprocess.run(["g++", "--version"], capture_output=True,
                                       text=True).stdout.splitlines()[0],
            "flags": "-O3 -std=c++17",
            "commit": _git("rev-parse", "--short", "HEAD"),
            "dirty": bool(_git("status", "--porcelain", "--", "../veriflow_fr",
                               "veriflow")),
            "measured": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "stopping_rule": "1 cold + %d warm passes over all edges" % WARM_PASSES,
            "timed": "affected ECs + their forwarding graphs, per edge, inside "
                     "the engine; no property check (Q11)",
        }),
    }


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bench", default="bench/wl_airtel1")
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)
    result = measure(args.bench)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w") as out:
            out.write(text + "\n")
    print(text)
    return 0 if result["gate_within_10x"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
