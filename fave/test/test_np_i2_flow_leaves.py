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

""" Parsing NetPlumber's reduced flow-tree dump into FaVe identities
(AD6_PLAN.md §5.5 "ROOT-CAUSING PLAN" step (c)).

Tested separately from the dump itself because the NetPlumber i2 build costs
~552 s: the expensive half writes raw output once, and this half is iterated
on. Every fixture here is the real output shape --
`{"flows": [{"node": id, "children": [{"node": id}, ...]}]}` with `children`
FLAT in simple mode (net_plumber.cc:1694 recurses into one array and appends
only leaves), and `children` ABSENT when the flow died at the source.

The distinction the whole comparison rests on: a leaf is any node with no
onward flow, so it is EITHER a probe arrival OR a dead end, and only the id
says which. Conflating them makes "ad6 forwarded past an NP leaf" trivially
true at every probe, which would have produced a confident wrong answer.
"""

import unittest

from bench.np_i2_flow_leaves import (
    leaf_ids, resolve_node, classify_leaves, load_inverse_maps
)


# A miniature of the real fave.json, using the REAL id scheme: probes and
# generators are small ints, and a rule node id packs its table as
# (table_id << 32) | index. Verified against the i2 dump.
#
# The first version of this fixture invented `id_to_rule` as a leaf->table map
# and every test passed against it -- self-consistent, and wrong. The real
# dump resolved through that map by numeric coincidence and produced
# `table#20971559`. Fixtures that agree with each other prove nothing about
# the format; these ids are copied from the real thing.
_T_IN_CHIC, _T_OUT_CHIC, _T_IN_KANS = 20, 21, 40


def _rule(table_id, index):
    return (table_id << 32) | index


_FAVE = {
    "id_to_table": {"20": "in.chic.1", "21": "out.chic.1", "40": "in.kans.1"},
    "id_to_generator": {"101": "source.chic"},
    "id_to_probe": {"93": "probe.chic"},
    "id_to_port": {"700": "out.chic.220047"},
    "mapping": {},
}


class TestLeafIds(unittest.TestCase):

    def test_a_flat_children_array_yields_its_leaves(self):
        tree = {"flows": [{"node": 101, "children": [{"node": _rule(_T_OUT_CHIC, 5)}, {"node": 93}]}]}
        self.assertEqual(leaf_ids(tree), [_rule(_T_OUT_CHIC, 5), 93])

    def test_a_source_flow_with_no_children_yields_nothing(self):
        """ `children` absent means the flow died at the source itself -- an
        empty leaf set, not a parse error. """
        self.assertEqual(leaf_ids({"flows": [{"node": 900}]}), [])

    def test_several_source_flows_are_all_collected(self):
        tree = {"flows": [{"node": 101, "children": [{"node": _rule(_T_OUT_CHIC, 5)}]},
                          {"node": 101, "children": [{"node": _rule(_T_IN_KANS, 7)}]}]}
        self.assertEqual(sorted(leaf_ids(tree)), sorted([_rule(_T_OUT_CHIC, 5), _rule(_T_IN_KANS, 7)]))

    def test_duplicate_leaves_are_preserved_as_branch_counts(self):
        """ NP emits one leaf per dying BRANCH, and the multiplicity is the
        signal -- wl_stanford's diagnosis was "868 branches die here, 1
        reaches the probe". Deduplicating would destroy that. """
        tree = {"flows": [{"node": 101, "children": [
            {"node": _rule(_T_OUT_CHIC, 5)}, {"node": _rule(_T_OUT_CHIC, 5)}, {"node": 93}]}]}
        self.assertEqual(leaf_ids(tree), [_rule(_T_OUT_CHIC, 5), _rule(_T_OUT_CHIC, 5), 93])

    def test_a_nested_children_array_is_still_walked(self):
        """ Defensive: full (non-simple) mode nests, and a caller who dumped
        without keep_simple should still get leaves rather than silence. """
        tree = {"flows": [{"node": 101, "children": [
            {"node": _rule(_T_IN_CHIC, 1), "children": [{"node": _rule(_T_OUT_CHIC, 5)}]}]}]}
        self.assertEqual(leaf_ids(tree), [_rule(_T_OUT_CHIC, 5)])

    def test_an_empty_children_array_makes_its_node_the_leaf(self):
        tree = {"flows": [{"node": 101, "children": [{"node": _rule(_T_OUT_CHIC, 5), "children": []}]}]}
        self.assertEqual(leaf_ids(tree), [_rule(_T_OUT_CHIC, 5)])


class TestResolveNode(unittest.TestCase):

    def setUp(self):
        self.inv = load_inverse_maps(_FAVE)

    def test_a_probe_id_resolves_as_a_probe(self):
        self.assertEqual(resolve_node(93, self.inv), ("probe", "probe.chic"))

    def test_a_generator_id_resolves_as_a_generator(self):
        self.assertEqual(resolve_node(101, self.inv), ("generator", "source.chic"))

    def test_a_rule_id_resolves_to_its_table(self):
        self.assertEqual(resolve_node(_rule(_T_OUT_CHIC, 5), self.inv), ("rule", "out.chic.1"))

    def test_a_table_id_resolves_as_a_table(self):
        """ A leaf may name a table directly rather than one of its rules.
        Probes and generators are still checked first, since their small ids
        shift down to table 0. """
        self.assertEqual(resolve_node(40, self.inv), ("table", "in.kans.1"))

    def test_an_unknown_id_resolves_as_unknown_not_a_guess(self):
        self.assertEqual(resolve_node(12345, self.inv), ("unknown", "12345"))

    def test_string_and_int_ids_resolve_alike(self):
        """ JSON object keys are strings while the dump's `node` values are
        numbers, so the maps must be indexable by either. """
        self.assertEqual(resolve_node("93", self.inv), ("probe", "probe.chic"))


class TestClassifyLeaves(unittest.TestCase):

    def setUp(self):
        self.inv = load_inverse_maps(_FAVE)

    def test_probe_leaves_are_delivered_and_others_are_dead_ends(self):
        summary = classify_leaves([93, _rule(_T_OUT_CHIC, 5), _rule(_T_OUT_CHIC, 5)], self.inv)
        self.assertEqual(summary["delivered"], {"probe.chic": 1})
        self.assertEqual(summary["dead_end"], {"out.chic.1": 2})

    def test_the_dead_end_tables_are_what_the_comparison_consumes(self):
        """ The device set ad6's witness walk is checked against: a device
        that appears here is one where NP's flow stops. """
        summary = classify_leaves([_rule(_T_OUT_CHIC, 5), _rule(_T_IN_KANS, 7), 93], self.inv)
        self.assertEqual(sorted(summary["dead_end_tables"]), ["in.kans.1", "out.chic.1"])

    def test_a_probe_only_leaf_set_has_no_dead_ends(self):
        summary = classify_leaves([93, 93], self.inv)
        self.assertEqual(summary["dead_end"], {})
        self.assertEqual(summary["delivered"], {"probe.chic": 2})

    def test_totals_are_reported(self):
        summary = classify_leaves([93, _rule(_T_OUT_CHIC, 5), _rule(_T_OUT_CHIC, 5), _rule(_T_IN_KANS, 7)], self.inv)
        self.assertEqual(summary["leaves_total"], 4)
        self.assertEqual(summary["delivered_total"], 1)
        self.assertEqual(summary["dead_end_total"], 3)

    def test_an_empty_leaf_set_is_reported_not_an_error(self):
        """ A source whose flow died immediately -- a real and interesting
        state, since it means the source injects nothing that survives. """
        summary = classify_leaves([], self.inv)
        self.assertEqual(summary["leaves_total"], 0)
        self.assertEqual(summary["dead_end_tables"], [])

    def test_unknown_ids_are_counted_separately_rather_than_silently_dropped(self):
        """ An unresolvable leaf means the id maps and the dump disagree,
        which invalidates the comparison -- it must be visible, not absorbed
        into the dead-end count. """
        summary = classify_leaves([93, 999999], self.inv)
        self.assertEqual(summary["unknown_total"], 1)
        self.assertEqual(summary["dead_end_total"], 0)


if __name__ == '__main__':
    unittest.main()
