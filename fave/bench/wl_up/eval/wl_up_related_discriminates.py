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

""" Does the structural model's answer actually depend on `related`?
(AD6_PLAN.md §9.23.3)

A targeted counterpart to wl_up_cchecks_by_category.py: that one scores the
whole policy, this one reads out the RAW reachability answer for a handful of
pairs under `related:0`, `related:1` and no condition at all.

The trick it turns on: `check_compliance` reports only VIOLATIONS, never the
underlying answer. So every (pair, cond) is submitted TWICE, once asserting
must-reach and once asserting must-not-reach. Exactly one of the two must fire,
and which one fired IS the answer -- no adapter change needed.

Expected, for a model that enforces FaVe's interweaved state shell:

    backward pair (server -> client)   related:0 -> False   related:1 -> True
    forward  pair (client -> server)   unconditioned -> True

i.e. return traffic passes, anything else backward does not.

Usage (from fave/, PYTHONPATH=.):
    python3 bench/wl_up/eval/wl_up_related_discriminates.py OUT.json [n_pairs]
"""

import json
import logging
import resource
import sys
import time

sys.setrecursionlimit(10**6)

from ad6.adapter import Ad6Adapter
from util.in_process_driver import InProcessFaVe

_PREFIX = "bench/wl_up"
_CONDS = ("related:0", "related:1", None)


def _cond(token):
    """ RuleField.to_json() shape. A raw string is silently DROPPED by
    fave_bridge._structural_state_literals -- see §9.23.2a. """
    if token is None:
        return []
    name, value = token.split(':', 1)
    return [{"name": name, "value": value, "negated": False}]


def _stateful_pairs(cchecks, limit):
    pairs = sorted({(source, probe) for source, entries in cchecks.items()
                    for probe, _valid, cond in entries if cond})
    return pairs[:limit]


def _flip(pair):
    """ The `(X)` cell's checks sit on the BACKWARD pair; its forward partner is
    a separate entry with source and probe roles swapped. """
    source, probe = pair
    return ("source." + probe.split('.', 1)[1], "probe." + source.split('.', 1)[1])


def main():
    out = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    with open("%s/cchecks.json" % _PREFIX) as raw:
        cchecks = json.load(raw)
    backward = _stateful_pairs(cchecks, limit)
    pairs = backward + [_flip(p) for p in backward]

    probes = [(s, p, t) for (s, p) in pairs for t in _CONDS]
    rules = {}
    for source, probe, token in probes:
        for negated in (False, True):
            rules.setdefault(probe, []).append([source, negated, _cond(token)])
    print("probing %d (pair,cond) combos = %d queries" % (
        len(probes), 2 * len(probes)), flush=True)

    started = time.time()
    log = logging.getLogger("wl_up_related_discriminates")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, translation="structural")
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

    # a violation with must_reach=True means the answer was False, and vice versa
    answer = {}
    for source, probe, must_reach, cond in violations:
        token = None
        if cond:
            field = cond[0] if isinstance(cond, list) else cond
            token = "%s:%s" % (field["name"], field["value"]) \
                if isinstance(field, dict) else str(field)
        answer[(source, probe, token)] = not must_reach

    rows = []
    print("\n%-46s %-42s %-10s %s" % ("source", "probe", "cond", "reachable"))
    for source, probe, token in probes:
        got = answer.get((source, probe, token), "MISSING")
        rows.append([source, probe, token, got])
        print("%-46s %-42s %-10s %s" % (source, probe, token, got))

    discriminating = sum(
        1 for pair in pairs
        if answer.get(pair + ("related:0",)) != answer.get(pair + ("related:1",)))
    print("\npairs whose answer DIFFERS between related:0 and related:1: %d of %d"
          % (discriminating, len(pairs)))
    print("%.1fs  peak %.1f GB" % (elapsed, peak))

    with open(out, "w") as raw:
        json.dump({"rows": rows, "discriminating_pairs": discriminating,
                   "pairs": len(pairs), "elapsed_s": round(elapsed, 1),
                   "peak_gb": round(peak, 2)}, raw, indent=2)
    print("wrote %s" % out)
    return 0 if discriminating == len(pairs) else 1


if __name__ == "__main__":
    sys.exit(main())
