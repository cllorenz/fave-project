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

Drives wl_stanford through NetPlumber twice: once with the shipped
`routes.json` rule order, and once with each declared FIB table RE-PRIORITISED
BY IP PREFIX LENGTH (longest prefix = highest priority = longest-prefix-match,
how a real router forwards). It reports the reachable-pair count for each.

Why: the real Stanford data plane does longest-prefix-match -- `bbra_rtr`'s FIB
forwards `172.28.0.0/14 -> 172.20.5.33` (toward rozb), a longer prefix than the
`172.16.0.0/12 -> Null0` drop and the `0.0.0.0/0` default. NetPlumber resolves
rule priority by rule index (lower index = higher priority), so a model fed in
file order rather than prefix-length order lets the default outrank the specific
route and NP under-reports reachability. That is what this script originally
demonstrated: re-prioritising lifted NP's count 10 -> ~165, confirming NP's
canonical "10/240" was a priority artifact and APKeep's LPM forwarding the
faithful one. See APKEEP_STANFORD_NP_SPEC.md.

**BOTH COLUMNS NOW READ 165, AND THAT IS THE FIX LANDING, NOT THE CHECK GOING
STALE.** `bench/np_preparation.py:_reprioritise_fib_lpm` re-prioritises the
declared FIB tables when the dataset is PREPARED, so the shipped `routes.json`
is already longest-prefix-first and the "file order" column is measuring an
already-corrected file. The A/B therefore no longer exhibits the bug -- it
asserts the absence of it. A DIVERGENCE between the two columns now means the
preparation step has regressed, which is exactly the tripwire worth keeping.
(For the record of how easily this hides: the same fix was scoped to `mid.*`
tables for a month, so it silently never applied to wl_i2 -- whose FIB is the
`out` stage -- leaving 3,731 rules there shadowed by an earlier containing
prefix. See AD6_PLAN.md §5.5.)

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


# wl_stanford's FIB stage. This harness is stanford-ONLY by construction (it
# loads the stanford model via C._load_model), so naming the stage here is
# correct rather than a hardcode -- but the SELECTION is shared with
# bench/np_preparation.py:fib_tables so the two cannot drift. They did drift
# once: np_preparation's own copy hardcoded `mid.` and therefore silently did
# nothing on wl_i2, whose FIB is the `out` stage (AD6_PLAN.md §5.5).
_STANFORD_FIB_TABLE_TYPES = ["mid"]


def _reprioritise_lpm(model) -> None:
    """ Reassign each FIB table's rule idx (field[2]) so longer prefixes get
    lower idx (= higher NP priority) -- longest-prefix-match. Stable within a
    prefix length. """
    from bench.np_preparation import fib_tables
    fibs = fib_tables(model["routes"], _STANFORD_FIB_TABLE_TYPES)
    by_dev = defaultdict(list)
    for route in model["routes"]:
        by_dev[route[0]].append(route)
    for dev, routes in by_dev.items():
        if dev not in fibs:
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
    print()
    print("The real Stanford FIBs forward by longest-prefix-match, so the LPM")
    print("count is the faithful data plane.")
    if file_order == lpm:
        print()
        print("The two agree, which is the EXPECTED result: np_preparation.py")
        print("re-prioritises the declared FIB tables when the dataset is")
        print("prepared, so the shipped routes.json is already longest-prefix-")
        print("first and the left-hand column measures an already-corrected")
        print("file. A DIVERGENCE here would mean that preparation step has")
        print("regressed. See APKEEP_STANFORD_NP_SPEC.md Phase 1, AD6_PLAN.md 5.5.")
    else:
        print()
        print("*** THEY DIFFER: the shipped routes.json is NOT longest-prefix-")
        print("first, so np_preparation.py's LPM re-prioritisation did not reach")
        print("these tables. Check config.json's 'fib_table_types' declaration --")
        print("that exact failure hid for a month on wl_i2. AD6_PLAN.md 5.5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
