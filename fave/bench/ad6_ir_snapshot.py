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

""" AD6_PLAN.md §9 Phase 0.2: characterization snapshots of
`Ad6Adapter._build_ir()`, one per benchmark and per measurement-relevant
configuration.

WHAT THESE ARE FOR, AND WHAT THEY ARE NOT. They are TRIPWIRES for the §9
adapter rewrite -- their only job is to make every change to the IR VISIBLE.
They are emphatically NOT a specification of correct output: the IR they pin
is the one produced by the adapter §9 exists to REPLACE, so a snapshot that
changes is a prompt to adjudicate, never by itself a regression. §9's Phase
0.3 fixes who adjudicates (NetPlumber's own matrix; on wl_i2 additionally
`bench/i2_structural_oracle.py`) precisely so that question is settled BEFORE
the first diff is seen rather than after.

A snapshot is a sha256 over the canonical IR plus a per-key SHAPE summary. The
hash alone answers "did anything move"; the shape answers "where", without
committing a 77k-rule structure to the repository. Both are needed: a bare
hash makes every diff a bisection.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/ad6_ir_snapshot.py --list
  python3 bench/ad6_ir_snapshot.py --bench wl_ifi
  python3 bench/ad6_ir_snapshot.py --all --out bench/ad6_ir_snapshots.json
  python3 bench/ad6_ir_snapshot.py --all --check bench/ad6_ir_snapshots.json
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import time

from typing import Any, Callable, Dict, List, Tuple


def _engine(faithful_vlan: bool = False, probe_untag: bool = False) -> Any:
    # AD6_PLAN.md §9.3 Phase 5: the adapter default flipped to 'structural' at
    # the Phase 5 gate. This driver's archived numbers were all measured on the
    # SEMANTIC path, so it pins that explicitly -- leaving it implicit would have
    # re-measured every one of them silently, which is exactly what the
    # generality-debt gate forbids (a measurement-affecting choice is a stamped
    # field, never a habit). Re-measuring structurally is a deliberate act: change
    # this line and re-run, do not inherit a new default.
    from ad6.adapter import Ad6Adapter, TRANSLATION_SEMANTIC
    log = logging.getLogger("ad6_ir_snapshot")
    log.setLevel(logging.WARNING)
    return Ad6Adapter(log, faithful_vlan=faithful_vlan, probe_untag=probe_untag,
                      translation=TRANSLATION_SEMANTIC)


def _replay(engine: Any, prefix: str, files: Any = None) -> Dict[str, Any]:
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        if files is None:
            fave.replay(prefix)
        else:
            fave.replay(prefix, files=files)
        return engine._build_ir()


# --- per-benchmark recipes ------------------------------------------------
# Each mirrors that benchmark's own existing test/driver setup exactly, so a
# snapshot is of the SAME model those already exercise -- not a second,
# separately-drifting way of building it.

def _ir_wl_ifi() -> Dict[str, Any]:
    return _replay(_engine(), "bench/wl_ifi")


def _ir_wl_up() -> Dict[str, Any]:
    # NOTE (§9 Phase 4): load_bench_metadata is what DISCARDS FaVe's parsed
    # rules for the 136 devices carrying a ruleset_path. It is called here on
    # purpose -- the snapshot has to pin the adapter as it stands, bypass and
    # all, or it cannot witness the bypass being removed.
    engine = _engine()
    engine.load_bench_metadata("bench/wl_up")
    return _replay(engine, "bench/wl_up")


_I2_FILES = {"topology": "device_topology.json", "routes": "routes.json",
             "policies": "probes.json", "sources": "sources.json"}


# Same prefix bench/ad6_i2_measure.py uses: wl_i2's replay inputs are the
# GENERATED i2-json/ tree, not the benchmark directory itself.
_I2_PREFIX = os.path.join("bench", "wl_i2", "i2-json")


def _ir_wl_i2(faithful_vlan: bool = False, probe_untag: bool = False) -> Dict[str, Any]:
    return _replay(_engine(faithful_vlan=faithful_vlan, probe_untag=probe_untag),
                   _I2_PREFIX, files=_I2_FILES)


def _ir_wl_stanford(routers: Any = None, faithful_vlan: bool = False) -> Dict[str, Any]:
    from bench.apkeep_convergence import (
        _FILES, _filter_model, _load_model, _write_model,
    )
    model = _load_model()
    if routers is not None:
        model = _filter_model(model, set(routers))
    tmp = tempfile.TemporaryDirectory(prefix="ad6_ir_snapshot_stanford_")
    try:
        _write_model(model, tmp.name)
        return _replay(_engine(faithful_vlan=faithful_vlan), tmp.name, files=_FILES)
    finally:
        tmp.cleanup()


_N2 = ("bbra_rtr", "rozb_rtr")

RECIPES: Dict[str, Callable[[], Dict[str, Any]]] = {
    "wl_ifi":                   _ir_wl_ifi,
    "wl_up":                    _ir_wl_up,
    "wl_i2_plain":              lambda: _ir_wl_i2(),
    "wl_i2_faithful":           lambda: _ir_wl_i2(faithful_vlan=True),
    "wl_i2_faithful_untag":     lambda: _ir_wl_i2(faithful_vlan=True, probe_untag=True),
    "wl_stanford_n2_plain":     lambda: _ir_wl_stanford(routers=_N2),
    "wl_stanford_n2_faithful":  lambda: _ir_wl_stanford(routers=_N2, faithful_vlan=True),
    "wl_stanford_n16_plain":    lambda: _ir_wl_stanford(),
    "wl_stanford_n16_faithful": lambda: _ir_wl_stanford(faithful_vlan=True),
}


def _canonical(ir: Dict[str, Any]) -> str:
    """ Stable across dict-insertion order and Python versions -- the hash has
    to answer "did the CONTENT move", not "did something get built in a
    different order". """
    return json.dumps(ir, sort_keys=True, separators=(",", ":"), default=str)


def _shape(value: Any) -> Any:
    """ One level of structure per IR key: a count for containers, the value
    itself for scalars. Enough to localize a diff without storing the IR. """
    if isinstance(value, dict):
        return {"type": "dict", "len": len(value),
                "nested": sum(len(v) for v in value.values()
                              if isinstance(v, (list, dict, str)))}
    if isinstance(value, list):
        return {"type": "list", "len": len(value)}
    return {"type": type(value).__name__, "value": value}


def snapshot(name: str) -> Dict[str, Any]:
    started = time.time()
    ir = RECIPES[name]()
    canonical = _canonical(ir)
    return {
        "bench": name,
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "bytes": len(canonical),
        "build_s": round(time.time() - started, 3),
        "keys": sorted(ir),
        "shape": {key: _shape(ir[key]) for key in sorted(ir)},
    }


def _compare(current: Dict[str, Any], stored: Dict[str, Any]) -> List[str]:
    if current["sha256"] == stored["sha256"]:
        return []
    diffs = ["sha256 %s -> %s" % (stored["sha256"][:12], current["sha256"][:12])]
    old_shape, new_shape = stored.get("shape", {}), current.get("shape", {})
    for key in sorted(set(old_shape) | set(new_shape)):
        if old_shape.get(key) != new_shape.get(key):
            diffs.append("  %s: %s -> %s" % (
                key, old_shape.get(key, "<absent>"), new_shape.get(key, "<absent>")))
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bench", action="append", default=None,
                        help="snapshot this benchmark (repeatable); default with --all is every recipe")
    parser.add_argument("--all", action="store_true", help="snapshot every recipe")
    parser.add_argument("--list", action="store_true", help="list recipe names and exit")
    parser.add_argument("--out", default=None, help="write the snapshots here as JSON")
    parser.add_argument("--check", default=None,
                        help="compare against a stored snapshot file; exit 1 on any difference")
    args = parser.parse_args()

    if args.list:
        for name in RECIPES:
            print(name)
        return 0

    names = list(RECIPES) if args.all else (args.bench or [])
    if not names:
        parser.error("give --bench NAME (repeatable), --all, or --list")
    unknown = [n for n in names if n not in RECIPES]
    if unknown:
        parser.error("unknown benchmark(s): %s -- see --list" % ", ".join(unknown))

    results = {}
    for name in names:
        snap = snapshot(name)
        results[name] = snap
        print("%-26s %s  %8d B  %6.1f s" % (
            name, snap["sha256"][:16], snap["bytes"], snap["build_s"]), file=sys.stderr)

    if args.out:
        with open(args.out, "w") as out:
            json.dump(results, out, indent=2, sort_keys=True)
            out.write("\n")
        print("wrote %s" % args.out, file=sys.stderr)

    if args.check:
        with open(args.check) as raw:
            stored = json.load(raw)
        failed = False
        for name in names:
            if name not in stored:
                print("NEW      %s (not in %s)" % (name, args.check))
                failed = True
                continue
            diffs = _compare(results[name], stored[name])
            if diffs:
                failed = True
                print("CHANGED  %s" % name)
                for line in diffs:
                    print("         %s" % line)
            else:
                print("same     %s" % name)
        if failed:
            print("\nA changed snapshot is a prompt to ADJUDICATE, not a regression by "
                  "itself -- see this module's docstring and AD6_PLAN.md §9 Phase 0.3.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
