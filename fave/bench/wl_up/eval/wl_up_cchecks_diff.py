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

""" ad6 differential against bench/wl_up/cchecks.json's real (source, probe,
valid, cond) compliance policy (AD6_PLAN.md §5.1).

Not a unittest (unlike test_ad6_wl_up.py's small hand-picked characterization)
because the full set is 11902 entries at ~0.5s/query -- a ~1-2 hour run. wl_up's
policy is built from 21 near-identically-structured org subnets, each carrying
the same {clients,file,mail,print,voip,web} role set against the same rule
templates (bench/wl_up/rulesets/*-ruleset), so per Claas's guidance a SAMPLE of
orgs (--mode sample, the default) is expected to be functionally representative
of the full set; --mode full is the final confirmation run, expected to find
nothing the sample didn't already show.

cchecks.json loading mirrors test_ad6_wl_ifi_stateful.py's _load_rules/
_cond_field exactly (same file shape, same source-keyed/probe-keyed inversion,
same "valid" (not "negated") polarity -- see that module's docstring for why
getting this backwards silently inverts almost every check into a false
"violation").

Usage (from fave/, PYTHONPATH=.):
    python3 bench/wl_up/eval/wl_up_cchecks_diff.py [--mode sample|full]
        [--orgs api,cs,...] [--out results.json]
"""

import argparse
import json
import logging
import os
import sys
import time

_PREFIX = "bench/wl_up"

# Central/singleton sources (adm, data, dns, ldap, pgf, vpn, the "internet"
# probe, and the org=="uni-potsdam" instance of file/mail/web) are always
# included -- there is exactly one of each, so there is no "sample" to take.
_ALWAYS_ORGS = {"uni-potsdam", None}

# Orgs sampled from the 21 near-identical per-org subnets (clients/file/mail/
# print/voip/web x 21), chosen for diversity of naming shape: "api" (the
# fullest role set -- clients/file/mail/print/voip/web all present), "cs" (a
# plain department), "sq-brandenburg" and "welcome-center-potsdam" (orgs whose
# own domain has no "uni-potsdam" component at all, a different address-space
# shape), "wifi" (missing print/voip roles entirely -- exercises the
# _inputs_present-style "not every org has every role" edge).
_DEFAULT_SAMPLE_ORGS = ("api", "cs", "sq-brandenburg", "welcome-center-potsdam", "wifi")


def _cond_field(token):
    name, value = token.split(':', 1)
    return {"name": name, "value": value, "negated": False}


def _is_stateful(cond):
    return bool(cond) and any(f.get("name") == "related" for f in cond)


def _load_rules(select=None):
    """ Returns (rules, kept_sources, total_sources). `select(source) -> bool`
    filters which sources' checks are included; None means all (the full
    11902-entry set). rules is {probe: [[source, negated, cond], ...]}, the
    shape check_compliance expects -- see test_ad6_wl_ifi_stateful.py's
    _load_rules docstring for the valid->negated polarity flip this performs. """
    with open("%s/cchecks.json" % _PREFIX) as raw:
        by_source = json.load(raw)
    rules = {}
    kept = set()
    for source, entries in by_source.items():
        if select is not None and not select(source):
            continue
        kept.add(source)
        for probe, valid, cond in entries:
            rules.setdefault(probe, []).append(
                [source, not valid, [_cond_field(c) for c in cond]])
    return rules, kept, set(by_source)


def _org_of(source):
    toks = source.split('.')
    return toks[2] if len(toks) > 2 else None


def _make_sample_selector(orgs):
    orgs = set(orgs)
    def _select(source):
        return _org_of(source) in _ALWAYS_ORGS or _org_of(source) in orgs
    return _select


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("sample", "full"), default="sample")
    ap.add_argument("--orgs", default=",".join(_DEFAULT_SAMPLE_ORGS),
                     help="comma-separated org names to sample (--mode sample only)")
    ap.add_argument("--out", default=None, help="write full violation list as JSON here")
    args = ap.parse_args()

    select = None if args.mode == "full" else _make_sample_selector(args.orgs.split(","))
    rules, kept_sources, all_sources = _load_rules(select)
    total_checks = sum(len(v) for v in rules.values())
    stateful_checks = sum(1 for v in rules.values() for e in v if _is_stateful(e[2]))

    print("mode=%s sources=%d/%d checks=%d (stateful=%d)" % (
        args.mode, len(kept_sources), len(all_sources), total_checks, stateful_checks))
    if select is not None:
        print("orgs sampled: %s (+ always-included singleton/central sources)" % args.orgs)
    sys.stdout.flush()

    from ad6.adapter import Ad6Adapter, available
    if not available():
        print("ad6 fave_bridge.py unavailable")
        return 1

    log = logging.getLogger("wl_up_cchecks_diff")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log)
    engine.load_bench_metadata(_PREFIX)

    from util.in_process_driver import InProcessFaVe

    start = time.time()
    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        fave.check_compliance(rules)
    elapsed = time.time() - start

    violations = engine.get_compliance_results()
    plain_violations = [v for v in violations if not _is_stateful(v[3] or [])]
    stateful_violations = [v for v in violations if _is_stateful(v[3] or [])]

    print("done in %.1fs (%.3fs/check)" % (elapsed, elapsed / max(total_checks, 1)))
    print("violations: %d total (plain=%d, stateful=%d)" % (
        len(violations), len(plain_violations), len(stateful_violations)))
    for v in violations[:50]:
        print("  VIOLATION source=%s probe=%s must_reach=%s cond=%s" % v)
    if len(violations) > 50:
        print("  ... (%d more, see --out)" % (len(violations) - 50))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({
                "mode": args.mode, "orgs": args.orgs if select is not None else None,
                "sources": sorted(kept_sources), "total_checks": total_checks,
                "stateful_checks": stateful_checks, "elapsed_s": elapsed,
                "violations": violations,
            }, fh, indent=2)
        print("wrote %s" % args.out)

    return 1 if violations else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
