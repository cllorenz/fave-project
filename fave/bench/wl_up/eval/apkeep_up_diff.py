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

""" APKeep-vs-NetPlumber differential for wl_up (APKEEP_NDD_PLAN.md Part 1.3/1.4).

The flagship correctness result for the FaVe/APKeep(BDD) backend: the full
136-device wl_up model built from zero through BOTH backends must agree on the
whole 137x137 source->probe reachability matrix (Phase D: 0 diffs, 3660/3660
reachable pairs). This harness reconstructs (and commits, out of scratchpad) the
throwaway driver that produced that number, so it reproduces on the pinned env
and serves as the differential ORACLE for the later NDD engine (an NDD backend
must reproduce this matrix pair-for-pair).

wl_up needs no `files=` replay override: its generated inputs already use the
default names (topology.json / routes.json / policies.json / sources.json).
Generate them first (from fave/, PYTHONPATH=.) if bench/wl_up/*.json are stale:

    bash scripts/generate-pgf-ruleset.sh    bench/wl_up   # only if rulesets/ empty
    bash scripts/generate-host-rulesets.sh  bench/wl_up
    bash scripts/generate-clients-rulesets.sh bench/wl_up
    PYTHONPATH=. python3 bench/wl_up/topogen.py     # topology.json + sources.json
    PYTHONPATH=. python3 bench/wl_up/routegen.py    # routes.json
    PYTHONPATH=. python3 bench/wl_up/policygen.py   # policies.json

Same two hard constraints as bench/apkeep_convergence.py force a **subprocess per
backend**: APKeep's resident JVM and NetPlumber's native lib cross-contaminate in
one process, and only one APKeep network fits per process. The driver spawns one
fresh `--emit` worker per backend and reads back each worker's matrix.

Comparison is by **full node name**, self-pairs excluded. Unlike the wl_stanford
convergence harness (where NP is the oracle and APKeep over-approximates), the
wl_up target is EXACT: both over- and under-approximation must be 0.

Usage:
  # full differential (both backends), print the exactness verdict:
  PYTHONPATH=. python3 bench/wl_up/eval/apkeep_up_diff.py
  # also persist the golden matrices next to this script (mat_apk.json/mat_np.json):
  PYTHONPATH=. python3 bench/wl_up/eval/apkeep_up_diff.py --save
  # one backend's matrix only (worker mode; used internally by the driver):
  PYTHONPATH=. python3 bench/wl_up/eval/apkeep_up_diff.py --emit apkeep --out /tmp/m.json

Set APKEEP_BUILD_PROFILE=<path> to stream the APKeep from-zero build curve as
JSONL (the timing side of Part 1.4); it is inert when unset.

Exit code: 0 iff the matrices are IDENTICAL (over==0 and under==0). Non-zero on
any divergence or a worker failure.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys

from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))          # .../fave/bench/wl_up/eval
FAVE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # .../fave
MODEL_DIR = os.path.join(FAVE, "bench", "wl_up")

Pair = Tuple[str, str]
Matrix = Dict[str, List[str]]   # probe full name -> sorted source full names that reach it


# ---- driving a backend (worker side) ----------------------------------------

def _make_engine(backend: str) -> Any:
    log = logging.getLogger("apkeep_up_diff")
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


def compute_matrix(backend: str) -> Matrix:
    """ Drive wl_up through `backend` and return the full-name reachability
    matrix probe -> [sources that reach it]. Must run in a dedicated process
    (see module docstring). """
    from util.in_process_driver import InProcessFaVe

    engine = _make_engine(backend)
    with InProcessFaVe(engine) as fave:
        fave.replay(MODEL_DIR)                 # default filenames; no files= override
        sources, probes = _names(engine)
        rules = {p: [[s, False, []] for s in sources] for p in probes}
        fave.check_compliance(rules)
    not_reached = _not_reached(engine)
    return {
        p: sorted(s for s in sources if (s, p) not in not_reached and s != p)
        for p in probes
    }


# ---- differential (driver side) ---------------------------------------------

def _pairs(matrix: Matrix) -> Set[Pair]:
    return {(s, p) for p, srcs in matrix.items() for s in srcs}


def _base(name: str) -> str:
    """ Strip the source./probe. role prefix to the host base, so a host's source
    and its own probe collapse to the same base (matches the wl_stanford
    convergence harness). """
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _meaningful(pairs: Set[Pair]) -> Set[Pair]:
    """ Drop host-to-self pairs (base(source) == base(probe)). A host reaching
    "itself" is not a compliance question; the frozen Phase D headline (3660)
    excludes the single such pair, source.clients.wifi -> probe.clients.wifi.
    (wl_tum keeps same-base pairs because its ONLY pair is source.tum->probe.tum;
    wl_up has 137 hosts, so self-exclusion is the right convention here.) """
    return {(s, p) for (s, p) in pairs if _base(s) != _base(p)}


def _emit_worker(backend: str, out: str) -> Tuple[Matrix, float]:
    """ Spawn a fresh process to compute one backend's matrix (isolation) and
    return (matrix, wall_seconds) -- the from-zero build+query wall for that
    backend on this env (Part 1.4). """
    from time import perf_counter
    argv = [sys.executable, os.path.abspath(__file__), "--emit", backend, "--out", out]
    env = dict(os.environ, PYTHONPATH=FAVE)
    start = perf_counter()
    proc = subprocess.run(argv, cwd=FAVE, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wall = perf_counter() - start
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
        raise RuntimeError("%s worker failed (rc=%d)" % (backend, proc.returncode))
    with open(out) as raw:
        return json.load(raw), wall


def run_differential(save: bool) -> int:
    import tempfile

    print("== APKeep-vs-NetPlumber differential (wl_up, full model) ==")
    with tempfile.TemporaryDirectory(prefix="apkeep_up_out_") as tmp:
        ap, ap_wall = _emit_worker("apkeep", os.path.join(tmp, "apkeep.json"))
        np, np_wall = _emit_worker("netplumber", os.path.join(tmp, "netplumber.json"))
    print("from-zero build+query wall: APKeep %.1f s   NetPlumber %.1f s   (%.1fx)"
          % (ap_wall, np_wall, ap_wall / np_wall if np_wall else 0.0))

    if save:
        for name, matrix in (("mat_apk.json", ap), ("mat_np.json", np)):
            with open(os.path.join(HERE, name), "w") as out:
                json.dump(matrix, out, indent=1, sort_keys=True)
        print("saved golden matrices: %s/{mat_apk.json,mat_np.json}" % HERE)

    ap_pairs, np_pairs = _pairs(ap), _pairs(np)
    over = ap_pairs - np_pairs      # APKeep says reachable, NP says not
    under = np_pairs - ap_pairs     # NP says reachable, APKeep drops it: unsound
    # Headline count uses meaningful (non-self) pairs to match the frozen Phase D
    # number; over/under are computed on the full set (self-pairs, agreed by both
    # backends, cannot create a divergence anyway).
    ap_m, np_m = _meaningful(ap_pairs), _meaningful(np_pairs)

    print("APKeep reachable pairs:     %d  (%d excl. host-to-self)" % (len(ap_pairs), len(ap_m)))
    print("NetPlumber reachable pairs: %d  (%d excl. host-to-self)" % (len(np_pairs), len(np_m)))
    print("OVER-APPROX  (apkeep \\ np): %d" % len(over))
    print("UNDER-APPROX (np \\ apkeep): %d" % len(under))

    for label, diffs in (("over-approximated (APKeep-only)", over),
                         ("under-approximated (NetPlumber-only, UNSOUND)", under)):
        if diffs:
            print("\n%s:" % label)
            for s, p in sorted(diffs)[:50]:
                print("  %s -> %s" % (s, p))
            if len(diffs) > 50:
                print("  ... (%d more)" % (len(diffs) - 50))

    exact = not over and not under
    print("\nDIFFERENTIAL: over=%d under=%d %s (%d/%d meaningful reachable pairs agree)" % (
        len(over), len(under), "EXACT" if exact else "DIVERGENT",
        len(ap_m & np_m), len(ap_m | np_m)))
    return 0 if exact else 1


# ---- entry point ------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emit", choices=("apkeep", "netplumber"),
                        help="worker mode: compute one backend's matrix and write it to --out")
    parser.add_argument("--out", help="worker mode: matrix output file")
    parser.add_argument("--save", action="store_true",
                        help="persist the golden matrices next to this script")
    args = parser.parse_args(argv)

    if args.emit:
        if not args.out:
            parser.error("--emit requires --out")
        matrix = compute_matrix(args.emit)
        with open(args.out, "w") as out:
            json.dump(matrix, out)
        return 0

    return run_differential(args.save)


if __name__ == "__main__":
    sys.exit(main())
