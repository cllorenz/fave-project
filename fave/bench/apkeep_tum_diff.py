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

""" APKeep-vs-NetPlumber convergence harness for wl_tum (APKEEP_TUM_UP_PLAN.md,
Phase 1).

wl_tum is a single stateful IPv4 firewall (fw.tum, ~3.8k rules) and ships an
*empty* oracle (reachable.json == {}), so NetPlumber is the reference: the
metric is APKeep's reachability over/under-approximation vs NP, driven to zero as
the adapter learns to model the conntrack `related` state field, the packet-
filter svlan/dvlan match fields, and the in_port/out_port rewrite (Phases 2-3).

Same two hard constraints as bench/apkeep_convergence.py force a **subprocess per
backend**: APKeep's resident JVM and NetPlumber's native lib cross-contaminate in
one process (NP then over-reports reachability), and only one APKeep network fits
per process. The driver spawns one fresh `--emit` worker per backend and reads
back each worker's matrix.

Unlike the stanford harness this compares by **full node name** (not router base)
and does NOT exclude same-base pairs: wl_tum's only pair is source.tum -> probe.tum,
whose bases both collapse to "tum", so a base-keyed self-reach exclusion would
silently drop the single meaningful reachability question (does an injected packet
traverse fw.tum's forward filter to the accept point?).

Usage:
  # full differential (both backends, over-approx + soundness):
  python bench/apkeep_tum_diff.py
  # one backend's matrix only (worker mode; used internally by the driver + test):
  python bench/apkeep_tum_diff.py --emit apkeep --out /tmp/m.json

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

from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
FAVE = os.path.dirname(HERE)                       # .../fave
MODEL_DIR = os.path.join(HERE, "wl_tum")

Pair = Tuple[str, str]
Matrix = Dict[str, List[str]]   # probe full name -> sorted source full names that reach it


# ---- driving a backend (worker side) ----------------------------------------

def _make_engine(backend: str) -> Any:
    log = logging.getLogger("apkeep_tum_diff")
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
    """ Drive wl_tum through `backend` and return the full-name reachability
    matrix probe -> [sources that reach it]. Must run in a dedicated process
    (see module docstring). """
    from util.in_process_driver import InProcessFaVe

    engine = _make_engine(backend)
    with InProcessFaVe(engine) as fave:
        fave.replay(MODEL_DIR)
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


def _emit_worker(backend: str, out: str) -> Matrix:
    """ Spawn a fresh process to compute one backend's matrix (isolation). """
    argv = [sys.executable, os.path.abspath(__file__), "--emit", backend, "--out", out]
    env = dict(os.environ, PYTHONPATH=FAVE)
    proc = subprocess.run(argv, cwd=FAVE, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
        raise RuntimeError("%s worker failed (rc=%d)" % (backend, proc.returncode))
    with open(out) as raw:
        return json.load(raw)


def run_differential() -> int:
    import tempfile

    print("== APKeep-vs-NetPlumber convergence (wl_tum) ==")
    with tempfile.TemporaryDirectory(prefix="apkeep_tum_out_") as tmp:
        ap = _emit_worker("apkeep", os.path.join(tmp, "apkeep.json"))
        np = _emit_worker("netplumber", os.path.join(tmp, "netplumber.json"))

    ap_pairs, np_pairs = _pairs(ap), _pairs(np)
    over = ap_pairs - np_pairs      # APKeep says reachable, NP says not
    under = np_pairs - ap_pairs     # NP says reachable, APKeep drops it: unsound

    print("APKeep reachable pairs:     %d" % len(ap_pairs))
    print("NetPlumber reachable pairs: %d  (reference oracle)" % len(np_pairs))
    print("OVER-APPROX  (apkeep \\ np): %d" % len(over))
    print("UNDER-APPROX (np \\ apkeep): %d   <- MUST be 0 (soundness)" % len(under))

    if over:
        print("\nover-approximated pairs (source -> probe), APKeep-only:")
        for s, p in sorted(over):
            print("  %s -> %s" % (s, p))
    if under:
        print("\n!! UNDER-APPROX: pairs NetPlumber reaches but APKeep drops:")
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
    args = parser.parse_args(argv)

    if args.emit:
        if not args.out:
            parser.error("--emit requires --out")
        matrix = compute_matrix(args.emit)
        with open(args.out, "w") as out:
            json.dump(matrix, out)
        return 0

    return run_differential()


if __name__ == "__main__":
    sys.exit(main())
