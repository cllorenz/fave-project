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

""" wl_ifi's REAL compliance policy (bench/wl_ifi/cchecks.json), including the
54 stateful `<->>` "related:0"/"related:1" checks, through Ad6Adapter
(AD6_PLAN.md §4.2).

Unlike test_ad6_wl_ifi.py (a hand-built all-pairs plain-reachability matrix,
cond=[] throughout, compared against reachable.json), this drives the exact
same (source, probe, negated, cond) tuples FaVe's own policy compiler produced
from reach.txt -- the tuples every other backend's check_compliance is also
handed. There is no independent (e.g. live NetPlumber) oracle wired up for
this yet -- no backend in this repo currently exercises the stateful subset
end-to-end, see AD6_PLAN.md §4.2's "what's missing" note -- so this is
currently a CHARACTERIZATION test, not a differential: it pins down ad6's
actual, traced-and-understood behaviour so a future regression is caught,
without yet claiming that behaviour is the ground truth.

Findings from tracing this the first time it ran (AD6_PLAN.md §4.2/
ad6/FAVE_CHANGES.md):
  * All 245 plain (cond=[]) checks pass with zero violations -- consistent
    with test_ad6_wl_ifi.py's exact match against reachable.json.
  * Of the 54 stateful checks (27 `<->>` pairs x {related:1, related:0}),
    the 27 related:1 ("must reach with ESTABLISHED") checks all pass, but
    all 27 related:0 ("must NOT reach with NEW") checks fail (ad6 reports
    reachable).
  * Traced ONE such pair (source.internal.ifi -> probe.admin.ifi) down to
    the actual captured ACL entry: engine._acl_out['464'] has
    [7424, True, '10.0.12.0/23', '10.0.14.0/23', None] -- a PERMIT rule
    with related=None, i.e. wl_ifi's real ACLs (parsed as-is from
    bench/wl_ifi/acls.txt's Cisco IOS text) carry NO ctstate/"established"
    qualifier on this rule at all. This is not a translation gap: there is
    no `related` match field on the source FaVe rule for
    favemodel.py/adapter.py to carry through -- the underlying permit is
    genuinely state-blind. Given that, "must reach with ESTABLISHED forced"
    and "must reach with NEW forced" necessarily get the SAME answer
    (reachable, via the one state-blind rule); related:1 happens to WANT
    that answer, related:0 does not, hence the perfectly systematic
    27-pass/27-fail split (every related:0 check fails, none partially).
  * OPEN QUESTION (needs the benchmark owner or a live NetPlumber
    differential to resolve, not guessed at here): does NetPlumber's own
    check_compliance evaluate a "related:N" cond the same way (a
    header-space/state-field constraint against the SAME state-blind ACL,
    which would make it agree with ad6 that these 27 are genuine policy
    violations already present in wl_ifi's real ACLs -- reach.txt's
    <->> intent was simply never implemented in acls.txt for these pairs),
    or does it resolve "related" through some other, topology/role-based
    mechanism this adapter hasn't accounted for? Until that's confirmed,
    treat the 27 as a known, understood, *possibly*-real property of the
    benchmark rather than a proven ad6 defect.

This is the first end-to-end exercise of ad6/fave_bridge.py's
`_state_literals` query-forcing (and favemodel.py's ACL `related` -> <state>
translation) through the real adapter/subprocess pipeline, rather than the
synthetic Kripke fixture in
ad6/test/core/instantiatortest.py:testStateLiteralForcingIsMutuallyExclusive.
"""

import json
import logging
import os
import unittest

from ad6.adapter import Ad6Adapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_ifi"

_INPUTS = [
    "%s/%s" % (_PREFIX, f) for f in
    ("topology.json", "routes.json", "sources.json", "policies.json", "cchecks.json")
]


def _inputs_present():
    return all(os.path.isfile(f) for f in _INPUTS)


def _cond_field(token):
    """ cchecks.json stores a condition as a bare "name:value" string (see
    bench/reach_csv_to_checks.py); the real check_compliance dispatch (via
    InProcessFaVe -> aggregator_service.py's `_handler`) instead expects the
    RuleField-JSON shape (`RuleField.from_json`) -- {"name", "value",
    "negated"} -- exactly as bench/compliance_checker.py's own `_parse_check`
    builds it from a raw checks.json entry. """
    name, value = token.split(':', 1)
    return {"name": name, "value": value, "negated": False}


def _load_rules():
    """ cchecks.json is keyed by SOURCE: {source: [[probe, valid, cond], ...]}
    -- bench/reach_csv_to_checks.py's `_generate_cchecks` stores `valid`
    (True = "must reach", the ABSENCE of a "!" prefix in the raw check
    string), NOT `negated`. check_compliance's (source, negated, cond) triple
    convention -- shared by every backend, e.g. this module's own
    Ad6Adapter.check_compliance computing `must_reach = not negated` -- is
    the OPPOSITE polarity (bench/compliance_checker.py's `_parse_check`
    builds its `rules` from a raw check string the same way: `negated = True`
    iff a literal "!" token is present). Loading cchecks.json's tuples
    in-place as (source, negated, cond) without flipping this bit inverts
    every single check's expected outcome -- confirmed the hard way: doing
    that once turned nearly every one of the 299 checks into a reported
    "violation". Also inverts source/probe -> probe-keyed (mirrors
    compliance_checker.py's own source-tuples -> probe-keyed `rules`
    inversion -- the wire format every backend's check_compliance expects). """
    with open("%s/cchecks.json" % _PREFIX) as raw:
        by_source = json.load(raw)
    rules = {}
    for source, entries in by_source.items():
        for probe, valid, cond in entries:
            rules.setdefault(probe, []).append(
                [source, not valid, [_cond_field(c) for c in cond]])
    return rules


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
class TestAd6WlIfiStateful(unittest.TestCase):
    """ ad6, driven by wl_ifi's real compliance policy (plain + stateful
    `<->>` checks alike). See the module docstring for what's proven here
    (the plain subset, and the query-forcing mechanism itself) vs. still
    open (whether the stateful subset's 27 failures are a genuine,
    pre-existing property of wl_ifi's real ACLs or a further modelling
    gap -- needs a live NetPlumber differential or the benchmark owner to
    resolve, not guessed at here). """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_ifi_stateful")
        log.setLevel(logging.WARNING)
        cls.engine = Ad6Adapter(log)
        cls.rules = _load_rules()

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            fave.check_compliance(cls.rules)

        cls.violations = cls.engine.get_compliance_results()

    @staticmethod
    def _is_stateful(cond):
        return bool(cond) and any(f.get("name") == "related" for f in cond)

    def test_check_set_matches_plan(self):
        """ Sanity: this is the same 299-entry/54-stateful check set
        AD6_PLAN.md §1.2's table records for wl_ifi. """
        total = sum(len(v) for v in self.rules.values())
        stateful = sum(
            1 for entries in self.rules.values()
            for e in entries if self._is_stateful(e[2]))
        self.assertEqual(total, 299)
        self.assertEqual(stateful, 54)

    def test_plain_checks_have_no_violations(self):
        """ The cond=[] subset: exact parity with test_ad6_wl_ifi.py's
        reachable.json-based result, via the real compliance policy this
        time instead of a synthetic all-pairs matrix. """
        plain_violations = [
            v for v in self.violations if not self._is_stateful(v[3] or [])]
        self.assertEqual(plain_violations, [])

    def test_stateful_checks_characterization(self):
        """ Pins down the CURRENT, traced-and-understood stateful result
        (module docstring) so a future change is caught as a diff, not
        silently absorbed. If this ever starts failing because the split
        changed shape, re-derive the story -- don't just update the
        numbers. """
        stateful_violations = [
            v for v in self.violations if self._is_stateful(v[3] or [])]
        self.assertEqual(len(stateful_violations), 27)
        self.assertTrue(
            all(f.get("value") == "0"
                for v in stateful_violations for f in v[3]
                if f.get("name") == "related"),
            "expected every stateful violation to be a related:0 (NEW) "
            "check -- the related:1 side has always passed so far")


if __name__ == '__main__':
    unittest.main()
