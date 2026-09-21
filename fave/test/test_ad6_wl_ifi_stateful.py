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

""" wl_ifi's REAL compliance policy (bench/wl_ifi/cchecks.json) through
Ad6Adapter: the 245 plain checks and the 54 stateful `related` ones are all
answered, and the stateful answers are the UNCONDITIONED ones -- because this
model has no `related` field for the condition to bind to.

WHAT CHANGED AT §9.37, AND IT IS A REVERSAL. This file used to pin a REFUSAL.
`fave_bridge` forced exactly one field and refused a `related` condition
against a model that declared none, on the reasoning that forcing nothing
answers the UNCONDITIONED question (§9.23.2a). That reasoning conflated two
opposite situations:

  * the model HAS the field and the condition was dropped -- §9.23's phantom
    finding, where `related:0` and `related:1` came back identical although
    they genuinely differ;
  * the model has NO such field, so every flow satisfies the condition and the
    two variants are identical BY CONSTRUCTION. Reporting that is correct.

The bridge now distinguishes them from the translator's `query_fields` recipe
map, which is authoritative about what the model constrains, so the second
case is honoured and announced instead of refused. `related` is an ordinary
8-bit header field in FaVe's model (§9.2a: `_interweave_state_shell` strips the
conntrack match and re-emits a plain `RuleField('related', ...)`), and wl_ifi
is the benchmark where FaVe puts them NOWHERE -- its ACLs come from Cisco IOS
text with no `established`/ctstate qualifier at all, so the interweaving has
nothing to strip. `test_the_model_really_has_no_related_field_to_bind` pins
that cause, and it is what licenses everything above.

MEASURED, and not on ad6's word alone: the 54 stateful checks now report 27
violations, which is exactly what NetPlumber reports for the same set, and
exactly the 27 CLOUD_BENCH_PLAN.md §1.9.0 records for wl_ifi under `<->>`
("the same data plane reports 27 violations under `<->>` and none under
`<-->`, because its Cisco ACLs really are stateless"). The deleted interpreted
path also produced 27/27, but by forcing ad6 `<state>` variables onto a
state-blind model -- a systematic split that looked like a finding and was an
artifact. The number is the same; what makes this one an answer rather than an
artifact is that the condition is honoured against a field the model provably
does not have, and that a second engine agrees.

NOTE WHAT IS *NOT* CLAIMED HERE: that a vacuous condition is a free pass. Where
a model DOES carry the field the condition is forced and the variants differ --
wl_up's 3,302 stateful checks are answered and agree exactly with NetPlumber
(§9.22/§9.23), and `test_ad6_bridge_cond.py` pins `related:0` against
`related:1` at unit level.

The old numbers are reproducible only by checking out commit 86114970: the
path that produced them was deleted at §9.25, and asking for it by name here
raises rather than quietly answering with this one.
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


def _is_stateful(cond):
    return bool(cond) and any(f.get("name") == "related" for f in cond)


def _split(rules):
    """ (plain, stateful), each in the probe-keyed check_compliance shape. """
    plain, stateful = {}, {}
    for probe, entries in rules.items():
        for entry in entries:
            target = stateful if _is_stateful(entry[2]) else plain
            target.setdefault(probe, []).append(entry)
    return plain, stateful


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
class TestAd6WlIfiStateful(unittest.TestCase):
    """ The two halves are driven SEPARATELY, because the stateful half raises:
    one combined call would abort before the plain half's verdicts could be
    read, and the plain result is the half that still has to hold. """

    @classmethod
    def setUpClass(cls):
        cls.rules = _load_rules()
        cls.plain, cls.stateful = _split(cls.rules)

    def _run(self, rules):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_ifi_stateful")
        log.setLevel(logging.CRITICAL)
        engine = Ad6Adapter(log)
        with InProcessFaVe(engine) as fave:
            fave.replay(_PREFIX)
            fave.check_compliance(rules)
            return engine.get_compliance_results()

    def test_check_set_matches_plan(self):
        """ Sanity: this is the same 299-entry/54-stateful check set
        AD6_PLAN.md §1.2's table records for wl_ifi. """
        total = sum(len(v) for v in self.rules.values())
        stateful = sum(len(v) for v in self.stateful.values())
        self.assertEqual(total, 299)
        self.assertEqual(stateful, 54)
        self.assertEqual(sum(len(v) for v in self.plain.values()), 245)

    def test_plain_checks_have_no_violations(self):
        """ The cond=[] subset: exact parity with test_ad6_wl_ifi.py's
        reachable.json-based result, via the real compliance policy this
        time instead of a synthetic all-pairs matrix. Unaffected by the
        stateful refusal -- which is the point of splitting them. """
        self.assertEqual(self._run(self.plain), [])

    def test_stateful_checks_are_answered(self):
        """ THE REVERSAL (§9.37). These used to raise. """
        violations = self._run(self.stateful)
        self.assertEqual(
            len(violations), 27,
            "the 54 stateful checks must answer 27 violations -- the number "
            "NetPlumber reports for the same set, and the one §1.9.0 records "
            "for wl_ifi under `<->>`")

    def test_the_condition_is_VACUOUS_here_and_that_is_demonstrated(self):
        """ What "honoured because there is nothing there" has to MEAN, checked
        rather than asserted: the same checks with the condition REMOVED must
        give the identical answer.

        This is deliberately the shape of the §9.23 bug, and the difference is
        the next test: there the field existed and the condition was dropped;
        here the model provably has no such field, so the two questions are the
        same question. Both halves are needed -- this one alone would pass for
        a dropped condition, and that one alone would not show the answers
        coincide. """
        stripped = {
            probe: [[source, negated, []] for source, negated, _cond in entries]
            for probe, entries in self.stateful.items()
        }
        # The (source, probe, must_reach) triple, not the whole tuple: the
        # fourth element is the engine's echo of the condition it was GIVEN,
        # which differs between the two runs by construction.
        pairs = lambda rules: sorted(
            (s, p, mr) for (s, p, mr, _c) in self._run(rules))
        self.assertEqual(pairs(self.stateful), pairs(stripped))

    def test_the_model_really_has_no_related_field_to_bind(self):
        """ Pins the CAUSE, not just the symptom: wl_ifi's Cisco ACLs carry no
        conntrack qualifier, so FaVe's interweaving emits no `related` rule and
        the model declares no such field. If this ever starts
        failing, the refusal above is no longer correct behaviour and the
        checks should be answered instead of refused. """
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_ifi_stateful")
        log.setLevel(logging.CRITICAL)
        engine = Ad6Adapter(log)
        with InProcessFaVe(engine) as fave:
            fave.replay(_PREFIX)
            fields = engine._build_literal()["mutable_fields"]

        self.assertNotIn("related", fields)
        related_matches = [
            field for tables in engine._tables.values()
            for rules in tables.values() for rule in rules
            for field in (getattr(rule, 'match', None) or [])
            if getattr(field, 'name', '') == 'related']
        self.assertEqual(related_matches, [],
                         "wl_ifi's model now carries `related` rules; the "
                         "stateful checks are answerable and this file's "
                         "premise has changed")


if __name__ == '__main__':
    unittest.main()
