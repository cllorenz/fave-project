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


""" wl_up's 11,902 compliance checks, decomposed by the FOUR categories FaVe
emits (AD6_PLAN.md §9.23).

`bench/reach_csv_to_checks.py:129-151` turns each cell of reachability.csv into
checks. An `X` cell is one unconditioned must-reach; an `(X)` cell -- the
backward half of FPL's `<->>` -- is TWO checks on that same backward pair, a
`related:1` must-reach and a `related:0` must-NOT-reach; anything else is an
unconditioned deny. So `<->>` imposes three checks in total, the initiation one
carrying NO `related` condition at all (Claas, 2026-09-15).

An aggregate violation count cannot distinguish these, which is how §9.23's
three analysis bugs went unnoticed: they produced plausible totals. This script
reports the breakdown instead.

TWO THINGS IT DELIBERATELY DOES NOT DO ITSELF (§9.23.5):

  * it IMPORTS `wl_up_cchecks_diff._load_rules` rather than re-reading
    cchecks.json. That file's second field is `valid`, NOT `negated`; a
    scratchpad driver that retyped the unpacking inverted every assertion and
    reported the SATISFIED checks as violations.

  * it builds each condition as a RuleField-shaped dict via that module's
    `_cond_field`. `fave_bridge._structural_state_literals` SILENTLY skips a
    condition that is not a dict, so passing the raw `['related:0']` strings
    from the JSON answers every stateful check as though it were unconditioned.

Usage (from fave/, PYTHONPATH=.):
    python3 bench/wl_up/eval/wl_up_cchecks_by_category.py OUT.json [structural|semantic]
"""

import collections
import json
import logging
import resource
import sys
import time

sys.setrecursionlimit(10**6)

from bench.wl_up.eval.wl_up_cchecks_diff import _load_rules
from ad6.adapter import Ad6Adapter
from util.in_process_driver import InProcessFaVe

_PREFIX = "bench/wl_up"

_KEYS = ("cat1-fwd-uncond-must-reach", "deny-uncond-must-NOT-reach",
         "cat2-bwd-rel1-must-reach", "cat3-bwd-rel0-must-NOT-reach")


def _token(cond):
    """ A violation's cond comes back as the dict list that was sent; the
    category index is keyed by the raw 'name:value' token cchecks.json uses. """
    if not cond:
        return None
    field = cond[0]
    if isinstance(field, dict):
        return "%s:%s" % (field["name"], field["value"])
    return str(field)


def _category_index():
    """ {(source, probe, cond_token): category} straight from cchecks.json. The
    cond token is part of the key because the two stateful checks of one `(X)`
    cell share a (source, probe) and differ ONLY in it. """
    with open("%s/cchecks.json" % _PREFIX) as raw:
        by_source = json.load(raw)
    index = {}
    for source, entries in by_source.items():
        for probe, valid, cond in entries:
            if not cond:
                key = "cat1-fwd-uncond-must-reach" if valid else "deny-uncond-must-NOT-reach"
            else:
                key = "cat2-bwd-rel1-must-reach" if valid else "cat3-bwd-rel0-must-NOT-reach"
            index[(source, probe, cond[0] if cond else None)] = key
    return index


def main():
    out = sys.argv[1]
    translation = sys.argv[2] if len(sys.argv) > 2 else "structural"

    rules, kept, _all = _load_rules(None)
    total = sum(len(v) for v in rules.values())
    index = _category_index()
    checks = collections.Counter(index.values())
    print("loaded %d checks over %d sources (translation=%s)" % (
        total, len(kept), translation), flush=True)

    started = time.time()
    log = logging.getLogger("wl_up_cchecks_by_category")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, translation=translation)
    # AD6_PLAN.md §9.25: `engine.load_bench_metadata(...)` was removed with the
    # semantic path. It re-read wl_up's raw ip6tables text so ad6's own parser
    # could re-parse rules FaVe had already parsed, discarding FaVe's state-shell
    # interweaving in the process; a structural translation takes them from the
    # model as delivered, which is what made wl_up agree with NetPlumber exactly.
    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        engine.check_compliance(rules)
        violations = engine.get_compliance_results()
    elapsed = time.time() - started
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1048576.0

    by_cat = collections.Counter()
    unclassified = []
    for source, probe, _must_reach, cond in violations:
        key = index.get((source, probe, _token(cond)))
        if key is None:
            unclassified.append((source, probe, _token(cond)))
        else:
            by_cat[key] += 1

    print("\n%-32s %8s %12s" % ("category", "checks", "violations"))
    for key in _KEYS:
        print("%-32s %8d %12d" % (key, checks[key], by_cat[key]))
    print("%-32s %8d %12d" % ("TOTAL", sum(checks.values()), len(violations)))
    if unclassified:
        print("UNCLASSIFIED: %d e.g. %s" % (len(unclassified), unclassified[:3]))
    print("\n%.1fs  peak %.1f GB" % (elapsed, peak))

    with open(out, "w") as raw:
        json.dump({"translation": translation,
                   "checks": dict(checks),
                   "violations_by_cat": dict(by_cat),
                   "total_violations": len(violations),
                   "unclassified": len(unclassified),
                   "elapsed_s": round(elapsed, 1),
                   "peak_gb": round(peak, 2)}, raw, indent=2)
    print("wrote %s" % out)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
