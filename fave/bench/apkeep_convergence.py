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

""" APKeep-vs-NetPlumber convergence harness (APKEEP_FAITHFUL_PLAN.md, Phase 0b).

The objective metric for the faithful-Stanford effort. It drives wl_stanford
through BOTH backends and reports the reachability **over-approximation** as a
single tracked number we watch shrink toward zero as APKeep's forwarding becomes
faithful, plus a hard **soundness** gate: APKeep must never drop a pair that
NetPlumber (the reference oracle) reports reachable (under-approximation must be
0). NetPlumber is the reference here -- reachable.json is the artificial
all-to-all policy, not the data plane (see stanford-forwarding-overapprox in the
project notes); NP's faithful HSA gives the true 10/240, cross-validated against
APKeep on wl_ifi where the two agree exactly.

Two hard constraints force a **subprocess per backend**:
  1. APKeep's resident JVM and NetPlumber's native lib cross-contaminate in one
     process (NP then wrongly reports full reachability); and
  2. only one APKeep network fits per process (the 100M-node BDD table).
So the driver spawns one fresh `--emit` worker per backend and reads back each
worker's matrix from a file.

Induced subsets: `--routers bbra_rtr,rozb_rtr` restricts the model to those
routers' in./mid./out. devices and the links among them (plus their sources/
probes) -- the tool Phase 0c uses to isolate a single divergence on a minimal
subnetwork instead of the full 16-router model.

CAVEAT on subset semantics: a naive induced subnetwork does NOT preserve the
full model's verdict for a pair -- removing the other routers removes forwarding
paths and the VLAN/route context that a full-model flow depends on, so it poses
a NEW, self-contained forwarding problem. It is therefore not a way to reproduce
a specific full-model pair's answer, but it IS a way to obtain a MINIMAL model in
which APKeep still over-approximates NetPlumber. Empirically `--routers
bbra_rtr,rozb_rtr` isolates the divergence to a single pair: NetPlumber reaches
rozb->bbra (edge->core, real) but not bbra->rozb (core->edge, blocked), while
APKeep reaches both -- so over_approx == {bbra->rozb}. That one-pair, two-router
model is the reproducer for the Phase 0c mechanism trace.

Usage:
  # full differential (both backends, over-approx + soundness):
  python bench/apkeep_convergence.py
  # restrict to an induced subnetwork:
  python bench/apkeep_convergence.py --routers bbra_rtr,goza_rtr
  # one backend's matrix only (worker mode; used internally by the driver):
  python bench/apkeep_convergence.py --emit apkeep --out /tmp/m.json [--routers ...]

Exit code: 0 iff soundness holds (under-approximation == 0). Non-zero if APKeep
under-approximates NetPlumber (a real path dropped) or a worker fails.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile

from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
FAVE = os.path.dirname(HERE)                       # .../fave
MODEL_DIR = os.path.join(HERE, "wl_stanford", "stanford-json")
# InProcessFaVe role -> filename for the wl_stanford naming.
_FILES = {
    "topology": "device_topology.json",
    "routes": "routes.json",
    "policies": "probes.json",
    "sources": "sources.json",
}

Pair = Tuple[str, str]
Matrix = Dict[str, List[str]]   # probe base -> sorted source bases that reach it


# ---- names ------------------------------------------------------------------

def _router_of(token: str) -> str:
    """ The router base of a device/port token: stage.<router>[.port].
    e.g. in.bbra_rtr -> bbra_rtr, out.goza_rtr.720006 -> goza_rtr,
    source.bbra_rtr.1 -> bbra_rtr. """
    return token.split('.')[1]


def _base(name: str) -> str:
    """ Strip a source./probe. role prefix down to the router base. """
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


# ---- model subsetting -------------------------------------------------------

def _load_model() -> Dict[str, Any]:
    def load(fn: str) -> Any:
        with open(os.path.join(MODEL_DIR, fn)) as raw:
            return json.load(raw)
    return {role: load(fn) for role, fn in _FILES.items()}


def _filter_model(model: Dict[str, Any], routers: Set[str]) -> Dict[str, Any]:
    """ Restrict every model file to devices/links/routes whose router base is in
    `routers` (links kept only when BOTH endpoints survive) -- an induced
    subnetwork. """
    def keep_dev(entry: Any) -> bool:
        return _router_of(entry[0]) in routers

    def keep_link(link: Any) -> bool:
        return _router_of(link[0]) in routers and _router_of(link[1]) in routers

    topo = model["topology"]
    sources = model["sources"]
    probes = model["policies"]
    return {
        "topology": {
            "devices": [d for d in topo["devices"] if keep_dev(d)],
            "links": [l for l in topo["links"] if keep_link(l)],
        },
        "routes": [r for r in model["routes"] if keep_dev(r)],
        "sources": {
            "devices": [d for d in sources["devices"] if keep_dev(d)],
            "links": [l for l in sources["links"] if keep_link(l)],
        },
        "policies": {
            "devices": [d for d in probes["devices"] if keep_dev(d)],
            "links": [l for l in probes["links"] if keep_link(l)],
        },
    }


def _write_model(model: Dict[str, Any], dest: str) -> None:
    for role, fn in _FILES.items():
        with open(os.path.join(dest, fn), "w") as out:
            json.dump(model[role], out)


# ---- driving a backend (worker side) ----------------------------------------

def _make_engine(backend: str) -> Any:
    log = logging.getLogger("apkeep_convergence")
    log.setLevel(logging.WARNING)
    if backend == "apkeep":
        from apkeep.adapter import APKeepAdapter
        return APKeepAdapter(log)
    if backend == "netplumber":
        from netplumber.lib_adapter import NetPlumberLibAdapter
        return NetPlumberLibAdapter(log)
    raise ValueError("unknown backend %r" % backend)


def _names(engine: Any) -> Tuple[List[str], List[str]]:
    from apkeep.adapter import APKeepAdapter
    if isinstance(engine, APKeepAdapter):
        return sorted(engine._generators), sorted(engine._probes)
    return sorted(engine.generators), sorted(engine.probes)


def _not_reached(engine: Any) -> Set[Pair]:
    from apkeep.adapter import APKeepAdapter
    results = engine.get_compliance_results()
    if isinstance(engine, APKeepAdapter):
        return {(s, p) for (s, p, _mr, _c) in results}
    sid = {info[1]: name for name, info in engine.generators.items()}
    pid = {info[1]: name for name, info in engine.probes.items()}
    return {(sid[s], pid[d]) for (s, d, _v, _c) in results if s in sid and d in pid}


def compute_matrix(backend: str, routers: Optional[Set[str]]) -> Matrix:
    """ Drive wl_stanford (optionally restricted to `routers`) through `backend`
    and return the base-name reachability matrix, self-reach excluded. Must run
    in a dedicated process (see module docstring). """
    from util.in_process_driver import InProcessFaVe

    model = _load_model()
    if routers is not None:
        model = _filter_model(model, routers)

    engine = _make_engine(backend)
    with tempfile.TemporaryDirectory(prefix="apkeep_conv_") as tmp:
        _write_model(model, tmp)
        with InProcessFaVe(engine) as fave:
            fave.replay(tmp, files=_FILES)
            sources, probes = _names(engine)
            rules = {p: [[s, False, []] for s in sources] for p in probes}
            fave.check_compliance(rules)
        not_reached = _not_reached(engine)
        return {
            _base(p): sorted(
                _base(s) for s in sources
                if (s, p) not in not_reached and _base(s) != _base(p)
            )
            for p in probes
        }


# ---- differential (driver side) ---------------------------------------------

def _pairs(matrix: Matrix) -> Set[Pair]:
    return {(s, p) for p, srcs in matrix.items() for s in srcs}


def _emit_worker(backend: str, routers: Optional[Set[str]], out: str) -> Matrix:
    """ Spawn a fresh process to compute one backend's matrix (isolation)."""
    argv = [sys.executable, os.path.abspath(__file__), "--emit", backend, "--out", out]
    if routers is not None:
        argv += ["--routers", ",".join(sorted(routers))]
    env = dict(os.environ, PYTHONPATH=FAVE)
    proc = subprocess.run(argv, cwd=FAVE, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
        raise RuntimeError("%s worker failed (rc=%d)" % (backend, proc.returncode))
    with open(out) as raw:
        return json.load(raw)


def run_differential(routers: Optional[Set[str]]) -> int:
    scope = "routers=%s" % ",".join(sorted(routers)) if routers else "full 16-router"
    print("== APKeep-vs-NetPlumber convergence (%s) ==" % scope)

    with tempfile.TemporaryDirectory(prefix="apkeep_conv_out_") as tmp:
        ap = _emit_worker("apkeep", routers, os.path.join(tmp, "apkeep.json"))
        np = _emit_worker("netplumber", routers, os.path.join(tmp, "netplumber.json"))

    ap_pairs, np_pairs = _pairs(ap), _pairs(np)
    over = ap_pairs - np_pairs      # APKeep says reachable, NP says not: the target
    under = np_pairs - ap_pairs     # NP says reachable, APKeep drops it: unsound

    print("APKeep reachable pairs:     %d" % len(ap_pairs))
    print("NetPlumber reachable pairs: %d  (reference oracle)" % len(np_pairs))
    print("OVER-APPROX  (apkeep \\ np): %d   <- the number to drive to 0" % len(over))
    print("UNDER-APPROX (np \\ apkeep): %d   <- MUST be 0 (soundness)" % len(under))

    if over:
        print("\nover-approximated pairs (source -> probe), APKeep-only:")
        for s, p in sorted(over):
            print("  %s -> %s" % (s, p))
    if under:
        print("\n!! UNSOUND: pairs NetPlumber reaches but APKeep drops:")
        for s, p in sorted(under):
            print("  %s -> %s" % (s, p))

    print("\nCONVERGENCE: over_approx=%d under_approx=%d %s" % (
        len(over), len(under), "SOUND" if not under else "UNSOUND"))
    return 1 if under else 0


# ---- entry point ------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emit", choices=("apkeep", "netplumber"),
                        help="worker mode: compute one backend's matrix and write it to --out")
    parser.add_argument("--out", help="worker mode: matrix output file")
    parser.add_argument("--routers", help="comma-separated router bases to restrict to "
                                          "(e.g. bbra_rtr,goza_rtr); default = all")
    args = parser.parse_args(argv)

    routers = set(args.routers.split(",")) if args.routers else None

    if args.emit:
        if not args.out:
            parser.error("--emit requires --out")
        matrix = compute_matrix(args.emit, routers)
        with open(args.out, "w") as out:
            json.dump(matrix, out)
        return 0

    return run_differential(routers)


if __name__ == "__main__":
    sys.exit(main())
