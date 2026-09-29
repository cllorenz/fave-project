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

""" FaVe model -> VeriFlow-FR, the translation half (VERIFLOW_PLAN.md V1).

Pure Python: the translation produces an engine-neutral IR, so every decision
of VERIFLOW_PLAN.md §7 that the adapter implements is pinned here, without the
native engine:

  * priority: FIRST-MATCH tables resolve by rule index, the lower winning, as
    NetPlumber's (`netplumber/adapter._prepare_generic_rule`); a table DECLARED
    longest-prefix-match orders longest prefix first, ties by index -- exactly
    `NetPlumberAdapter._lpm_ordered_batch` (Q9);
  * a rule with several ingress ports becomes one engine rule per port, at the
    same priority, and the factor is stamped (Q16);
  * a graph node is a FaVe table (Q20); IN_PORT is a matched field (Q7);
  * a generator's header space is the product of its per-field value lists,
    each a query set, started where its links enter the network (Q21);
  * a probe is a table with one consuming rule, its match (Q8);
  * negated check conditions expand into non-negated sets (Q17), refused on a
    must-reach check;
  * what V1 does not support is REFUSED, never approximated: router and
    packet-filter models, rewrites and negated rule fields arrive with V3.
"""

import unittest

from devices.generator import GeneratorModel
from devices.probe import ProbeModel
from devices.switch import SwitchModel
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField
from veriflow.translate import (
    ANY_PORT, Translator, Unsupported, expand_negated, node_edges
)


def _dst(prefix):
    return Match([RuleField("packet.ipv4.destination", prefix)])


def _rule(node, idx, prefix, out, in_ports=None):
    return Rule(node, node + ".1", idx, in_ports=in_ports or [],
                match=_dst(prefix), actions=[Forward(out)])


def _feed(tr, *models):
    for m in models:
        tr.add_tables(m)
        tr.add_wiring(m)
        tr.add_rules(m)


def _switch(node, ports, rules, lpm=False):
    model = SwitchModel(node, ports=ports, rules=rules)
    if lpm:
        model.table_semantics = {node + ".1": "lpm"}
    return model


class TestPriority(unittest.TestCase):

    def test_first_match_is_lower_index_wins(self):
        tr = Translator()
        _feed(tr, _switch("s1", ["1", "2"], [
            _rule("s1", 5, "10.0.0.0/8", ["s1.1"]),
            _rule("s1", 2, "10.1.0.0/16", ["s1.2"]),
        ]))
        ir = tr.translate()
        by_idx = {ir.origin[r.id][2]: r.priority for r in ir.rules}
        self.assertGreater(by_idx[2], by_idx[5])

    def test_declared_lpm_is_longest_prefix_first_ties_by_index(self):
        tr = Translator()
        _feed(tr, _switch("s1", ["1", "2"], [
            _rule("s1", 1, "10.0.0.0/8", ["s1.1"]),
            _rule("s1", 2, "10.1.0.0/16", ["s1.2"]),
            _rule("s1", 3, "10.2.0.0/16", ["s1.2"]),
            _rule("s1", 4, "0.0.0.0/0", ["s1.1"]),
        ], lpm=True))
        ir = tr.translate()
        order = [ir.origin[r.id][2] for r in
                 sorted(ir.rules, key=lambda r: -r.priority)]
        self.assertEqual(order, [2, 3, 1, 4])


    def test_inverted_lpm_exists_only_to_show_the_guard_can_fail(self):
        tr = Translator(invert_lpm=True)
        _feed(tr, _switch("s1", ["1", "2"], [
            _rule("s1", 1, "10.0.0.0/8", ["s1.1"]),
            _rule("s1", 2, "10.1.0.0/16", ["s1.2"]),
        ], lpm=True))
        ir = tr.translate()
        order = [ir.origin[r.id][2] for r in
                 sorted(ir.rules, key=lambda r: -r.priority)]
        self.assertEqual(order, [1, 2])
        self.assertTrue(ir.stamps["vf_invert_lpm"])


class TestPorts(unittest.TestCase):

    def test_several_ingress_ports_expand_at_the_same_priority(self):
        tr = Translator()
        _feed(tr, _switch("s1", ["1", "2", "3"], [
            _rule("s1", 1, "10.0.0.0/8", ["s1.3"], in_ports=["s1.1", "s1.2"]),
            _rule("s1", 2, "0.0.0.0/0", ["s1.3"]),
        ]))
        ir = tr.translate()
        self.assertEqual(len(ir.rules), 3)
        expanded = [r for r in ir.rules if ir.origin[r.id][2] == 1]
        self.assertEqual(sorted(r.in_port for r in expanded),
                         sorted([ir.ports["s1.1"], ir.ports["s1.2"]]))
        self.assertEqual(len({r.priority for r in expanded}), 1)
        self.assertEqual(ir.stamps["vf_inport_expansion"], 1.5)
        any_port = [r for r in ir.rules if ir.origin[r.id][2] == 2]
        self.assertEqual(any_port[0].in_port, ANY_PORT)

    def test_a_table_is_a_node_and_links_join_ports(self):
        tr = Translator()
        _feed(tr, _switch("s1", ["1"], []), _switch("s2", ["1"], []))
        tr.add_links_bulk([("s1.1", "s2.1")])
        ir = tr.translate()
        self.assertEqual(ir.port_table[ir.ports["s1.1"]], ir.tables["s1.1"])
        self.assertIn((ir.ports["s1.1"], ir.ports["s2.1"]), ir.links)
        self.assertEqual(ir.stamps["vf_node"], "table")


    def test_node_edges_are_delta_nets_graph(self):
        # DN §4.3.2's graph: a node per (switch, ingress port), an edge where a
        # rule at a node forwards to a port linked into another node. Edges into
        # a probe are FaVe's delivery wiring, not part of it.
        tr = Translator()
        _feed(tr,
              _switch("s1", ["1", "2", "3"], [
                  _rule("s1", 1, "10.0.0.0/8", ["s1.2"], in_ports=["s1.1"]),
                  _rule("s1", 2, "0.0.0.0/0", ["s1.3"], in_ports=["s1.1"])]),
              _switch("s2", ["1"], []))
        tr.add_probe(ProbeModel("probe.p", "existential"))
        tr.add_links_bulk([("s1.2", "s2.1"), ("s1.3", "probe.p.1")])
        ir = tr.translate()
        self.assertEqual(node_edges(ir), [
            (ir.tables["s1.1"], ir.ports["s1.1"], ir.ports["s2.1"])])


class TestSourcesAndProbes(unittest.TestCase):

    def test_generator_query_sets_and_starts(self):
        tr = Translator()
        _feed(tr, _switch("s1", ["1", "2"], []))
        tr.add_generator(GeneratorModel("source.a", fields={
            "ipv4_dst": [RuleField("ipv4_dst", "10.0.0.0/8"),
                         RuleField("ipv4_dst", "11.0.0.0/8")]}))
        tr.add_links_bulk([("source.a.1", "s1.1")])
        ir = tr.translate()
        starts, sets = ir.generators["source.a"]
        self.assertEqual(starts, [(ir.tables["s1.1"], ir.ports["s1.1"])])
        self.assertEqual(len(sets), 2)
        self.assertTrue(all(len(s) == 32 for s in sets))
        self.assertTrue(sets[0].startswith("00001010") and sets[0].endswith("x"))

    def test_probe_is_a_consuming_table(self):
        tr = Translator()
        _feed(tr, _switch("s1", ["1"], []))
        tr.add_probe(ProbeModel("probe.b", "existential"))
        tr.add_links_bulk([("s1.1", "probe.b.1")])
        ir = tr.translate()
        table = ir.probes["probe.b"]
        consuming = [r for r in ir.rules if r.table == table]
        self.assertEqual(len(consuming), 1)
        self.assertTrue(consuming[0].consume)
        self.assertEqual(ir.port_table[ir.ports["probe.b.1"]], table)


class TestNegatedConditions(unittest.TestCase):

    def test_a_negated_field_expands_to_single_bit_sets(self):
        # dport != 80 on 16 bits: one set per fixed bit of 80, that bit flipped.
        sets = expand_negated("x" * 16, 0, "0000000001010000")
        self.assertEqual(len(sets), 16)
        self.assertIn("1" + "x" * 15, sets)
        self.assertIn("x" * 9 + "0" + "x" * 6, sets)


class TestRefusals(unittest.TestCase):
    """ V1 refuses what it cannot translate faithfully (VERIFLOW_PLAN.md §10). """

    def test_a_router_model_is_refused(self):
        tr = Translator()
        model = _switch("r1", ["1"], [])
        model.type = "router"
        _feed(tr, model)
        with self.assertRaisesRegex(Unsupported, "router"):
            tr.translate()

    def test_a_rewrite_is_refused(self):
        rule = Rule("s1", "s1.1", 1, match=_dst("10.0.0.0/8"), actions=[
            Rewrite([RuleField("packet.ether.vlan", "7")]), Forward(["s1.1"])])
        tr = Translator()
        _feed(tr, _switch("s1", ["1"], [rule]))
        with self.assertRaisesRegex(Unsupported, "rewrite"):
            tr.translate()

    def test_a_negated_rule_field_is_refused(self):
        rule = Rule("s1", "s1.1", 1, match=Match([
            RuleField("packet.ipv4.destination", "10.0.0.0/8", negated=True)]),
            actions=[Forward(["s1.1"])])
        tr = Translator()
        _feed(tr, _switch("s1", ["1"], [rule]))
        with self.assertRaisesRegex(Unsupported, "negat"):
            tr.translate()

    def test_what_is_delivered_is_translated_not_what_the_model_becomes(self):
        # The aggregator extends its first model object per device in place
        # (bench/feature_survey.py found this); the translator snapshots.
        tr = Translator()
        model = _switch("s1", ["1"], [_rule("s1", 1, "10.0.0.0/8", ["s1.1"])])
        _feed(tr, model)
        model.tables["s1.1"].append(_rule("s1", 2, "11.0.0.0/8", ["s1.1"]))
        self.assertEqual(len(tr.translate().rules), 1)


if __name__ == '__main__':
    unittest.main()
