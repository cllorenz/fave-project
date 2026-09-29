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

""" VeriFlow-FR's EC census, against APKeep's Table 3 (VERIFLOW_PLAN.md V2).

WHAT IS COUNTED. VeriFlow's ECs over the WHOLE header space: per field, the
ranges that the boundaries of all rules' matches cut (T p.37), and their
cartesian product -- the count, never the ECs themselves (`ec_count`). That is
the set a bulk check whose source injects every header must slice (Q21). Two
views per workload:

  * **fib** -- the declared longest-prefix-match tables, the destination field
    only. On a single field VeriFlow's non-minimal ranges are exactly the
    intervals Delta-net's atoms are, so this is directly comparable with the
    Delta-netMF column of APKeep's Table 3 (NSDI'20);
  * **all** -- every rule of every model, every field it matches: the
    multi-field product, where range-based ECs explode (APKeep §5.3).

Also reported: the two expansion factors a VeriFlow-style engine pays -- FaVe's
own port-range-to-prefix expansion (rules per ruleset line, from the feature
survey) and ingress-port expansion (Q16, rules per FaVe rule).

Usage, from fave/ with PYTHONPATH=. and the venv active, after the workloads'
test/gen_*_inputs.sh and veriflow_fr/python/build_libveriflow_fr.sh:

    FAVE_ALLOW_OUT_IFACE=1 python3 bench/veriflow_ec_census.py [--json out.json]
"""

import argparse
import json
import os
import sys

from typing import Any, Dict, List, Optional

_F = {"topology": "device_topology.json", "policies": "probes.json"}

#: (name, prefix, files, APKeep Table 3 row it corresponds to, Delta-netMF's
#: count there, what the correspondence rests on)
WORKLOADS = [
    ("wl_airtel1", "bench/wl_airtel1", None, "Airtel1", 2799,
     "the same trace (bench/deltanet/TRACES.md)"),
    ("wl_airtel2", "bench/wl_airtel2", None, "Airtel2", 2799,
     "the same trace"),
    ("wl_stanford", "bench/wl_stanford/stanford-json", _F, "Stanford*", 2283,
     "the same hassel data; Stanford* is its IP forwarding alone, 3.84e3 rules "
     "in APKeep's Table 1, 3,844 here"),
    ("wl_i2", "bench/wl_i2/i2-json", _F, "Internet2", 22212,
     "NOT the same data: APKeep's Internet2 has 1.26e5 forwarding rules "
     "(Table 1), wl_i2 77,451"),
    ("wl_cloud", "bench/wl_cloud", None, None, None, ""),
    ("wl_ifi", "bench/wl_ifi", None, None, None, ""),
    ("wl_up", "bench/wl_up", None, None, None, ""),
    ("wl_tum", "bench/wl_tum", None, None, None, ""),
]

DST = "packet.ipv4.destination"


def _count(layout: List[Any], sets: List[str]) -> Dict[str, Any]:
    from veriflow.adapter import libveriflow_fr
    net = libveriflow_fr.Network(layout)
    net.add_table(1)
    for i, t in enumerate(sets, 1):
        net.load_rule(i, 1, 0, libveriflow_fr.ANY_PORT, t, [], False)
    per_field, exact, approx = net.ec_count('x' * sum(w for _n, w in layout))
    return {"fields": [n for n, _w in layout], "ranges_per_field": per_field,
            "ecs": exact, "ecs_approx": approx}


def census(prefix: str, files: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    from bench.feature_survey import RecordingEngine, raise_thread_errors, survey
    from util.in_process_driver import InProcessFaVe
    from veriflow.translate import Translator

    tr = Translator()
    with raise_thread_errors():
        with InProcessFaVe(tr) as fave:
            fave.replay(prefix, files=files)
    rec = RecordingEngine()
    with raise_thread_errors():
        with InProcessFaVe(rec) as fave:
            fave.replay(prefix, files=files)
    surveyed = survey(rec)

    out: Dict[str, Any] = {}
    layout, sets, rules = tr.match_sets()
    out["all"] = dict(_count(layout, sets), rules=rules)
    has_lpm = any(v == "lpm" for m in tr._models  # pylint: disable=protected-access
                  for v in m.table_semantics.values())
    if has_lpm:
        layout, sets, rules = tr.match_sets(lpm_only=True, fields=[DST])
        out["fib"] = dict(_count(layout, sets), rules=rules)
    r = surveyed["rules"]
    out["inport_expansion"] = round(r["in_port_expanded"] / r["total"], 3) if r["total"] else 1.0
    out["range_expansion"] = surveyed["expansion"]
    return out


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", default=None)
    parser.add_argument("--only", default=None, help="comma-separated workload names")
    args = parser.parse_args(argv)
    wanted = set(args.only.split(",")) if args.only else None

    results = {}
    for name, prefix, files, row, published, basis in WORKLOADS:
        if wanted and name not in wanted:
            continue
        if not os.path.isdir(prefix):
            results[name] = {"skipped": "inputs not generated"}
            continue
        res = census(prefix, files)
        if row:
            res["apkeep_table3"] = {"row": row, "delta_netmf": published, "basis": basis,
                                    "fib_equals": res.get("fib", {}).get("ecs") == published}
        results[name] = res
        fib = res.get("fib", {}).get("ecs")
        print("%-12s all %-14s %s  fib %s%s" % (
            name, "{:.3g}".format(res["all"]["ecs_approx"]),
            res["all"]["ranges_per_field"], fib,
            "  (Table 3 %s: %s)" % (row, published) if row else ""))
    if args.json:
        with open(args.json, "w") as out:
            json.dump(results, out, indent=2, sort_keys=True)
            out.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
