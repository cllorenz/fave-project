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

""" The workload feature survey (VERIFLOW_PLAN.md V0; TODO item 31).

The survey records what a verification engine is HANDED -- it sits where an
engine sits, behind the aggregator -- and classifies it. These tests pin the
classification before the survey exists (test-first, VERIFLOW_PLAN.md §8), so a
number in the survey means what these say it means:

  * a field value is classified by its BIT VECTOR, the form every engine sees:
    ANY (all wildcard), EXACT (no wildcard), PREFIX (wildcards only at the end),
    or TERNARY (anything else). A NEGATED value is its own kind, because no
    engine represents it directly -- NetPlumber expands it into several vectors;
  * `vf_fields` (VERIFLOW_PLAN.md D6) puts a field in the TRIE if any rule
    constrains it with an arbitrary wildcard (prefix, ternary, or a negation,
    whose expansion is ternary), in the SCAN set if every rule leaves it ANY or
    matches it exactly, and in UNUSED if no rule constrains it at all.
"""

import unittest

import threading

from bench.feature_survey import (
    RecordingEngine, classify_field, classify_vector, raise_thread_errors,
    survey, survey_checks, vf_fields
)
from devices.generator import GeneratorModel
from devices.switch import SwitchModel
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField


class TestClassifyVector(unittest.TestCase):
    """ The four kinds of a ternary bit vector. """

    def test_all_wildcard_is_any(self):
        self.assertEqual(classify_vector("xxxx"), "any")

    def test_no_wildcard_is_exact(self):
        self.assertEqual(classify_vector("0101"), "exact")

    def test_trailing_wildcards_are_a_prefix(self):
        self.assertEqual(classify_vector("01xx"), "prefix")

    def test_a_wildcard_before_a_fixed_bit_is_ternary(self):
        self.assertEqual(classify_vector("x1x0"), "ternary")
        self.assertEqual(classify_vector("0x1x"), "ternary")

    def test_single_bits(self):
        self.assertEqual(classify_vector("x"), "any")
        self.assertEqual(classify_vector("1"), "exact")

    def test_commas_from_the_vector_notation_are_ignored(self):
        # FaVe writes vectors in 8-bit groups ("xxxxxxxx,0000...") in places.
        self.assertEqual(classify_vector("0000,xxxx"), "prefix")


class TestClassifyField(unittest.TestCase):
    """ A RuleField is classified through FaVe's own bit-vector conversion. """

    def test_ipv4_prefix(self):
        self.assertEqual(
            classify_field(RuleField("packet.ipv4.destination", "10.0.0.0/8")),
            "prefix")

    def test_ipv4_host_is_exact(self):
        self.assertEqual(
            classify_field(RuleField("packet.ipv4.destination", "10.1.2.3")),
            "exact")

    def test_transport_port_is_exact(self):
        self.assertEqual(
            classify_field(RuleField("packet.upper.dport", "80")), "exact")

    def test_a_named_port_is_exact(self):
        # Port-typed fields carry a port NAME, which an adapter resolves to a
        # number later; before that it still denotes exactly one port.
        self.assertEqual(
            classify_field(RuleField("in_port", "ifi.1_ingress")), "exact")

    def test_negation_is_its_own_kind(self):
        self.assertEqual(
            classify_field(
                RuleField("packet.upper.dport", "80", negated=True)),
            "negated")


class TestVfFields(unittest.TestCase):
    """ D6's classification, from per-field kind counts. """

    def test_the_three_buckets(self):
        kinds = {
            "packet.ipv4.destination": {"prefix": 5, "exact": 2},
            "packet.upper.dport": {"exact": 3, "any": 9},
            "packet.ether.vlan": {"any": 4},
            "packet.ipv4.source": {"ternary": 1},
            "packet.ipv6.proto": {"negated": 1, "exact": 1},
        }
        self.assertEqual(vf_fields(kinds), {
            "trie": ["packet.ipv4.destination", "packet.ipv4.source",
                     "packet.ipv6.proto"],
            "scan": ["packet.upper.dport"],
            "unused": ["packet.ether.vlan"],
        })


def _switch():
    """ One switch: a /8 route, a host route with a VLAN rewrite, and a rule
    qualified by ingress port that floods to two ports. """
    rules = [
        Rule("s1", "s1.1", 0,
             match=Match([RuleField("packet.ipv4.destination", "10.0.0.0/8")]),
             actions=[Forward(["s1.2"])]),
        Rule("s1", "s1.1", 1,
             match=Match([RuleField("packet.ipv4.destination", "10.1.2.3")]),
             actions=[Rewrite([RuleField("packet.ether.vlan", "7")]),
                      Forward(["s1.3"])]),
        Rule("s1", "s1.1", 2, in_ports=["s1.1", "s1.2"],
             match=Match([RuleField("packet.upper.dport", "22")]),
             actions=[Forward(["s1.2", "s1.3"])]),
    ]
    return SwitchModel("s1", ports=["1", "2", "3"], rules=rules)


class TestRecordingEngine(unittest.TestCase):
    """ The recorder takes what the aggregator hands an engine, and the survey
    counts it. Driven directly with a hand-built model, so no workload and no
    native dependency is needed. """

    @classmethod
    def setUpClass(cls):
        eng = RecordingEngine()
        model = _switch()
        eng.add_tables(model)
        eng.add_wiring(model)
        eng.add_rules(model)
        eng.add_generator(GeneratorModel(
            "g1", fields={"ipv4_src": [RuleField("ipv4_src", "10.0.0.0/8")]}))
        eng.add_links_bulk([("s1.2", "s2.1"), ("s1.3", "s3.1")])
        cls.result = survey(eng)

    def test_devices_and_rules(self):
        self.assertEqual(self.result["devices"], {"switch": 1})
        self.assertEqual(self.result["rules"]["total"], 3)

    def test_field_kinds(self):
        self.assertEqual(self.result["fields"], {
            "packet.ipv4.destination": {"prefix": 1, "exact": 1},
            "packet.upper.dport": {"exact": 1},
        })

    def test_rewrites_are_counted_by_field_and_mask(self):
        self.assertEqual(self.result["rewrites"],
                         {"packet.ether.vlan": {"full": 1}})

    def test_rewrite_kinds(self):
        # full: set to one value; masked: set some bits, keep others (NAT to a
        # subnet); clear: set to ANY -- FaVe forgets its in_port/out_port
        # metadata this way at post-routing, which no VeriFlow action does.
        from bench.feature_survey import classify_rewrite
        self.assertEqual(classify_rewrite(
            RuleField("packet.ipv4.destination", "10.0.0.1")), "full")
        self.assertEqual(classify_rewrite(
            RuleField("packet.ipv4.destination", "10.0.0.0/24")), "masked")
        self.assertEqual(classify_rewrite(
            RuleField("out_port", "x" * 32)), "clear")

    def test_forwarding_shape(self):
        rules = self.result["rules"]
        self.assertEqual(rules["in_port_qualified"], 1)
        # A rule qualified by TWO ingress ports is a disjunction, which one
        # OpenFlow match cannot express: VeriFlow-FR would expand it.
        self.assertEqual(rules["multi_in_port"], 1)
        self.assertEqual(rules["in_port_expanded"], 4)
        self.assertEqual(rules["multi_port_forward"], 1)
        self.assertEqual(rules["drop"], 0)

    def test_table_semantics_default_is_first_match(self):
        self.assertEqual(self.result["semantics"], {"first_match": 1})

    def test_links_and_generators(self):
        self.assertEqual(self.result["links"], 2)
        self.assertEqual(self.result["generators"]["count"], 1)
        self.assertEqual(self.result["generators"]["fields"],
                         {"packet.ipv4.source": {"prefix": 1}})

    def test_vf_fields(self):
        self.assertEqual(self.result["vf_fields"], {
            "trie": ["packet.ipv4.destination"],
            "scan": ["packet.upper.dport"],
            "unused": [],
        })


class TestSurveyChecks(unittest.TestCase):
    """ Checks reach an engine through check_compliance, not the replay, so the
    recorder never sees them; they are surveyed from checks.json. A leading `!`
    makes a check must-NOT-reach; `f=!field:value` negates a condition FIELD
    (bench/compliance_checker.py), and a negated field is where the suite's
    negations actually live. """

    def test_counts_and_condition_kinds(self):
        checks = [
            "s=source.a && EF p=probe.b",
            "! s=source.a && EF p=probe.c",
            "s=source.a && EF p=probe.d && f=related:1 && f=port:80",
            "s=source.a && EF p=probe.e && f=!port:332",
        ]
        self.assertEqual(survey_checks(checks), {
            "count": 4,
            "must_reach": 3,
            "must_not_reach": 1,
            "conditioned": 2,
            "fields": {
                "packet.upper.dport": {"exact": 1, "negated": 1},
                "related": {"exact": 1},
            },
        })


class TestFailsLoudly(unittest.TestCase):
    """ A survey must never report a partial model. The aggregator applies
    commands on a worker THREAD, so an exception there used to print a traceback
    and leave the main thread writing a survey with, e.g., no links at all. """

    def test_a_worker_thread_exception_is_raised_in_the_caller(self):
        def boom():
            raise RuntimeError("worker failed")

        with self.assertRaisesRegex(RuntimeError, "worker failed"):
            with raise_thread_errors():
                worker = threading.Thread(target=boom)
                worker.start()
                worker.join()

    def test_no_error_no_raise(self):
        with raise_thread_errors():
            worker = threading.Thread(target=lambda: None)
            worker.start()
            worker.join()

    def test_what_is_delivered_is_counted_not_what_the_model_becomes(self):
        # The aggregator keeps the FIRST model object per device and later
        # extends it in place with the rules of the next command for that device
        # (aggregator_service: `model.tables[table].extend(model._adds[table])`),
        # while the engine is handed only the diff. Holding a reference counted
        # those rules twice -- 79,000 on wl_airtel1, whose model has 39,500.
        eng = RecordingEngine()
        model = _switch()
        eng.add_rules(model)
        model.tables["s1.1"].append(Rule(
            "s1", "s1.1", 3,
            match=Match([RuleField("packet.ipv4.destination", "10.2.0.0/16")]),
            actions=[Forward(["s1.2"])]))
        self.assertEqual(survey(eng)["rules"]["total"], 3)

    def test_global_port_is_stable_and_distinct(self):
        eng = RecordingEngine()
        first = eng.global_port("s1.1")
        self.assertEqual(eng.global_port("s1.1"), first)
        self.assertNotEqual(eng.global_port("s1.2"), first)


if __name__ == '__main__':
    unittest.main()
