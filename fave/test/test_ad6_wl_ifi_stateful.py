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
Ad6Adapter: the 245 plain checks are answered, the 54 stateful `related`
checks are REFUSED, and this pins both.

WHAT CHANGED AT THE §9.3 PHASE 5 GATE. The adapter's default translation is
now 'structural', and under it wl_ifi's stateful subset is UNANSWERABLE. This
file used to be a CHARACTERIZATION of the semantic path's answer to those
checks (27 pass / 27 fail, AD6_PLAN.md §4.2's open question); the open question
is now closed as MALFORMED, by owner decision, and the file pins the refusal
instead.

WHY THE CHECKS CANNOT BE ANSWERED, and why that is the better answer.
`related` is an ordinary 8-bit header field in FaVe's model -- §9.2(a):
fave/iptables/generator.py's `_interweave_state_shell` STRIPS the conntrack
matches and re-emits the derived rules carrying a plain `RuleField('related',
...)`, so a structural translation carries the state semantics for free
wherever FaVe put them. wl_ifi is the benchmark where FaVe puts them NOWHERE:
its ACLs are parsed from Cisco IOS text (bench/wl_ifi/acls.txt) that contains
no `established`/ctstate qualifier at all, so the interweaving has nothing to
strip and emits no `related` rule. The structural model consequently declares
no `related` field -- `mutable_fields` is {in_port, out_port, vlan} -- and
ad6/fave_bridge.py's `_structural_state_literals` refuses the condition rather
than forcing nothing and answering the UNCONDITIONED question (§9.23.2a).

The semantic path did answer them, by forcing ad6 `<state>` variables onto
that same state-blind model: both `related:1` and `related:0` necessarily
resolved through the one state-blind permit, so all 27 related:1 checks passed
and all 27 related:0 checks failed -- a perfectly systematic split that looked
like a finding about wl_ifi's ACLs and was an artifact of asking a question the
model cannot represent. Refusing is the honest answer to a malformed question.

NOTE WHAT IS *NOT* CLAIMED HERE: that ad6 cannot answer stateful checks. It
can, and does -- wl_up's 3,302 stateful checks are answered structurally and
agree exactly with NetPlumber (§9.22/§9.23), because wl_up's rulesets are real
ip6tables text whose `ctstate ESTABLISHED` FaVe's interweaving turns into real
`related` rules. The gap is wl_ifi's input data, not the translation.

Reproducing the old numbers is still possible without editing anything:
pass translation=TRANSLATION_SEMANTIC (see test_ad6_translation_flag.py).
"""

import json
import logging
import os
import unittest

from ad6.adapter import Ad6Adapter, available
from test.backend_gate import require_or_skip
from util.barrier import BarrierError

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

    def test_stateful_checks_are_REFUSED_not_answered(self):
        """ THE POINT OF THIS FILE since Phase 5. The failure that must never
        come back is a SILENT one: nothing forced, the unconditioned question
        answered, and a confident count returned (AD6_PLAN.md §9.23). So this
        asserts the refusal AND that it names the missing field, rather than
        merely asserting that something went wrong. """
        with self.assertRaises(BarrierError) as caught:
            self._run(self.stateful)

        message = str(caught.exception)
        self.assertIn("related", message)
        self.assertIn("declares no 'related' field", message)
        self.assertIn("UNCONDITIONED", message,
                      "the refusal must still explain WHY answering anyway "
                      "would be wrong -- that reasoning is the whole guard")

    def test_the_model_really_has_no_related_field_to_bind(self):
        """ Pins the CAUSE, not just the symptom: wl_ifi's Cisco ACLs carry no
        conntrack qualifier, so FaVe's interweaving emits no `related` rule and
        the structural model declares no such field. If this ever starts
        failing, the refusal above is no longer correct behaviour and the
        checks should be answered instead of refused. """
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_ifi_stateful")
        log.setLevel(logging.CRITICAL)
        engine = Ad6Adapter(log)
        with InProcessFaVe(engine) as fave:
            fave.replay(_PREFIX)
            fields = engine._build_structural()["mutable_fields"]

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
