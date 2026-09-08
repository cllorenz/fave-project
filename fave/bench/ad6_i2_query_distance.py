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

""" AD6_PLAN.md Sec 5.5 C2 follow-up: cheap graph-distance check for the
"hardness tracks topological distance" hypothesis from the 2026-09-08
Cadical195 query_log finding (losa<->newy32aoa hardest in both directions,
hous-anchored pairs fastest). Reuses the SAME Kripke graph the acyclic-rank
encoding is built over (KripkeStructure.IterFTransitions), treating any edge
either flag can fire as a graph edge -- the same convention AD6_PLAN.md's own
giant-SCC analysis already uses -- and computes a plain unweighted BFS
shortest-path hop-count from each query's source node to its destination
node. No SAT solving at all: only the Kripke build (~5-6 min, the same
dominant cost every C1/C2 run already pays) plus near-instant BFS over
78,078 nodes/155,199 edges. Correlates hop-count against the elapsed_s
values already recorded in eval/ad6_i2_cadical195_lite_72pairs_complete_v2.json's
query_log, instead of running any solver again.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/ad6_i2_query_distance.py
"""

import json
import os
import sys
from collections import deque

sys.setrecursionlimit(10 ** 6)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_FAVE)
_AD6 = os.path.join(_ROOT, 'ad6')

_I2_PREFIX = os.path.join("bench", "wl_i2", "i2-json")
_TIMING = os.path.join(_HERE, "wl_i2", "eval", "ad6_i2_cadical195_lite_72pairs_complete_v2.json")


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _build_ir():
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe
    import logging

    log = logging.getLogger("ad6_i2_query_distance")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, faithful_vlan=False)

    files = {"topology": "device_topology.json", "routes": "routes.json",
             "policies": "probes.json", "sources": "sources.json"}
    with InProcessFaVe(engine) as fave:
        fave.replay(_I2_PREFIX, files=files)
        sources = sorted(engine._generators)
        probes = sorted(engine._probes)
        ir = engine._build_ir()
    return ir, sources, probes


def _bfs_distance(kripke, start):
    """ Unweighted BFS from `start` over ALL Kripke edges (both flags --
    matches AD6_PLAN.md Sec 5.5's own giant-SCC convention: "any edge either
    direction can fire" counts as a graph edge). Returns {node: hop_count}. """
    dist = {start: 0}
    q = deque([start])
    while q:
        node = q.popleft()
        d = dist[node]
        for target, _flag in kripke.IterFTransitions(node):
            if target not in dist:
                dist[target] = d + 1
                q.append(target)
    return dist


def _bfs_backward_set(kripke, start):
    """ All ancestors of `start` -- nodes that can reach it via SOME chain of
    forward transitions -- found by walking IterBTransitions (predecessors)
    outward from `start`. This is the "could plausibly appear on ANY witness
    path to destination" set, as opposed to _bfs_distance's shortest-path-only
    view -- a candidate for why hop-count (shortest path) didn't predict
    elapsed_s: a query's real solve difficulty may depend on how many nodes
    COULD be involved (which is what the acyclic rank machinery has to keep
    consistent), not how far the nearest one is. """
    seen = {start}
    q = deque([start])
    while q:
        node = q.popleft()
        for pred, _flag in kripke.IterBTransitions(node):
            if pred not in seen:
                seen.add(pred)
                q.append(pred)
    return seen


def main():
    from ad6.adapter import Ad6Adapter  # noqa: F401 (import-order sanity, mirrors ad6_i2_measure.py)

    ir, sources, probes = _build_ir()
    print("[build] devices=%d sources=%d probes=%d" % (len(ir["devices"]), len(sources), len(probes)),
          file=sys.stderr)

    sys.path.insert(0, _AD6)
    from src.parser import favemodel
    from src.xml.xmlutils import XMLUtils

    cwd = os.getcwd()
    os.chdir(_AD6)
    try:
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, _encoding = favemodel.instantiate_base(config, ir)
        print("[build] kripke_nodes=%d" % len(list(kripke.IterNodes())), file=sys.stderr)

        # AD6_PLAN.md Sec 5.5's own giant-SCC probe computed distances from the
        # gen_entry_key/query_destination_key nodes the real queries use, not
        # arbitrary device names -- mirror that exactly so distances line up
        # 1:1 with query_log's (source, probe) pairs.
        source_nodes = {s: favemodel.gen_entry_key(s) for s in sources}
        probe_nodes = {p: favemodel.query_destination_key(p, ir) for p in probes}

        # Fan-out/fan-in size: the EXACT literal count each query's OR-gate
        # clause gets (ad6_i2_measure.py's own f_trans/b_trans, or_gate()) --
        # a mechanistic candidate now that plain hop-count (below) turned out
        # not to predict elapsed_s.
        fanout = {s: len(list(kripke.IterFTransitions(source_nodes[s]))) for s in sources}
        fanin = {p: len(list(kripke.IterBTransitions(probe_nodes[p]))) for p in probes}

        # One BFS per distinct source node (9 sources, not 72 queries) --
        # cheap regardless, reused across all of that source's destinations.
        bfs_cache = {}
        distances = {}
        for s in sources:
            snode = source_nodes[s]
            if snode not in bfs_cache:
                bfs_cache[snode] = _bfs_distance(kripke, snode)
            dist_from_s = bfs_cache[snode]
            for p in probes:
                if _base(s) == _base(p):
                    continue
                pnode = probe_nodes[p]
                distances[(s, p)] = dist_from_s.get(pnode)  # None if unreachable in the plain graph sense

        # Reachable-intersection idea: forward-reachable-from-source (already
        # have the node SET as bfs_cache[snode].keys(), no extra BFS needed)
        # intersected with backward-reachable-TO-probe (one more BFS per
        # distinct probe, 9 total) -- "how many nodes could plausibly appear
        # on ANY witness path for this query", not just the shortest one.
        backward_cache = {}
        intersect_size = {}
        for p in probes:
            pnode = probe_nodes[p]
            if pnode not in backward_cache:
                backward_cache[pnode] = _bfs_backward_set(kripke, pnode)
        for s in sources:
            snode = source_nodes[s]
            fwd_set = bfs_cache[snode].keys()
            for p in probes:
                if _base(s) == _base(p):
                    continue
                pnode = probe_nodes[p]
                intersect_size[(s, p)] = len(fwd_set & backward_cache[pnode])
    finally:
        os.chdir(cwd)

    missing = sum(1 for v in distances.values() if v is None)
    print("[distance] pairs=%d missing_path=%d" % (len(distances), missing), file=sys.stderr)

    timing = json.load(open(_TIMING))
    timing_by_pair = {(q["source"], q["probe"]): q["elapsed_s"] for q in timing["query_log"]}

    rows = []
    for (s, p), d in distances.items():
        t = timing_by_pair.get((s, p))
        if d is not None and t is not None:
            rows.append((_base(s), _base(p), d, fanout[s], fanin[p], fanout[s] + fanin[p],
                         intersect_size[(s, p)], t))

    print("%-14s %-14s %6s %8s %7s %9s %10s %10s" % (
        "source", "probe", "hops", "fanout", "fanin", "fan_sum", "isect", "elapsed_s"))
    for s, p, d, fo, fi, fsum, isect, t in sorted(rows, key=lambda r: -r[7]):
        print("%-14s %-14s %6d %8d %7d %9d %10d %10.1f" % (s, p, d, fo, fi, fsum, isect, t))

    def _corr(xs, ys):
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
        sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
        sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
        return cov / (sx * sy) if sx and sy else float("nan")

    n = len(rows)
    hops = [r[2] for r in rows]
    fouts = [r[3] for r in rows]
    fins = [r[4] for r in rows]
    fsums = [r[5] for r in rows]
    isects = [r[6] for r in rows]
    times = [r[7] for r in rows]
    print()
    print("n=%d  hop range=[%d, %d]  fanin range=[%d, %d]  isect range=[%d, %d]" % (
        n, min(hops), max(hops), min(fins), max(fins), min(isects), max(isects)))
    print("corr(hops, elapsed_s)    = %.3f" % _corr(hops, times))
    print("corr(fanout, elapsed_s)  = %.3f" % _corr(fouts, times))
    print("corr(fanin, elapsed_s)   = %.3f" % _corr(fins, times))
    print("corr(fan_sum, elapsed_s) = %.3f" % _corr(fsums, times))
    print("corr(isect, elapsed_s)   = %.3f" % _corr(isects, times))


if __name__ == "__main__":
    sys.exit(main())
