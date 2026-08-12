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

""" Stanford priority ground-truth check (APKEEP_FAITHFUL_PLAN.md Phase 1).

Drives wl_stanford through NetPlumber twice: once as the FaVe model builds it
(rule priority = tf.json FILE ORDER, via bench/np_preparation.py `cnt`), and once
with each mid-stage FIB table RE-PRIORITISED BY IP PREFIX LENGTH (longest prefix =
highest priority = longest-prefix-match, how a real router forwards). It reports
the reachable-pair count for each.

Why: the real Stanford data plane does longest-prefix-match -- `bbra_rtr`'s FIB
forwards `172.28.0.0/14 -> 172.20.5.33` (toward rozb), a longer prefix than the
`172.16.0.0/12 -> Null0` drop and the `0.0.0.0/0` default. NetPlumber resolves
rule priority by rule index (lower index = higher priority) and the FaVe model
feeds it rules in file order, NOT prefix-length order, so NP's default outranks
the specific route and NP under-reports reachability. Re-prioritising by prefix
length restores LPM and NP's count jumps (10 -> ~165 at the time of writing),
confirming NP's canonical "10/240" is a priority artifact and APKeep's LPM
forwarding is the faithful one. See APKEEP_STANFORD_NP_SPEC.md.

Usage:  PYTHONPATH=. python bench/stanford_priority_check.py
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apkeep_convergence as C   # noqa: E402


def _prefix_len(rule) -> int:
    """ IP-prefix length of a route's ipv4_dst match; -1 for match-all/no-dst. """
    for clause in rule[3]:
        if clause.startswith("ipv4_dst="):
            pfx = clause.split("=", 1)[1]
            return int(pfx.split("/")[1]) if "/" in pfx else 32
    return -1


def _reprioritise_lpm(model) -> None:
    """ Reassign each mid.* table's rule idx (field[2]) so longer prefixes get
    lower idx (= higher NP priority) -- longest-prefix-match. Stable within a
    prefix length. """
    by_dev = defaultdict(list)
    for route in model["routes"]:
        by_dev[route[0]].append(route)
    for dev, routes in by_dev.items():
        if not dev.startswith("mid."):
            continue
        order = sorted(range(len(routes)), key=lambda i: -_prefix_len(routes[i]))
        for new_idx, i in enumerate(order, start=1):
            routes[i][2] = new_idx


def _np_reachable_count(lpm: bool) -> int:
    logging.disable(logging.CRITICAL)
    from netplumber.lib_adapter import NetPlumberLibAdapter
    from util.in_process_driver import InProcessFaVe

    model = C._load_model()
    if lpm:
        _reprioritise_lpm(model)

    engine = NetPlumberLibAdapter(logging.getLogger("stanford_priority_check"))
    with tempfile.TemporaryDirectory(prefix="stanford_prio_") as tmp:
        C._write_model(model, tmp)
        with InProcessFaVe(engine) as fave:
            fave.replay(tmp, files=C._FILES)
            sources = sorted(engine.generators)
            probes = sorted(engine.probes)
            rules = {p: [[s, False, []] for s in sources] for p in probes}
            fave.check_compliance(rules)

    sid = {info[1]: name for name, info in engine.generators.items()}
    pid = {info[1]: name for name, info in engine.probes.items()}
    not_reached = {(sid[s], pid[d]) for (s, d, _v, _c) in engine.get_compliance_results()
                   if s in sid and d in pid}
    reach = {(C._base(s), C._base(p)) for s in sources for p in probes
             if (s, p) not in not_reached and C._base(s) != C._base(p)}
    return len(reach)


def main() -> int:
    # Each backend build must be its own process (resident-JVM / native-lib
    # isolation); run the two NP builds sequentially here (NP only, no JVM).
    file_order = _np_reachable_count(lpm=False)
    lpm = _np_reachable_count(lpm=True)
    print("NetPlumber reachable pairs:")
    print("  file-order priority (as the FaVe model feeds it): %d" % file_order)
    print("  prefix-length priority (longest-prefix-match):    %d" % lpm)
    print()
    print("The real Stanford FIBs forward by longest-prefix-match, so the LPM")
    print("count is the faithful data plane. NP's file-order count under-reports")
    print("(non-LPM priority artifact). See APKEEP_STANFORD_NP_SPEC.md Phase 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
