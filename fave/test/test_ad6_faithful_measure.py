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

""" The wl_stanford driver's provenance stamps (AD6_PLAN.md generality-debt
items 1/2/8).

`bench/ad6_faithful_measure.py` hardcodes its solver and offers no acyclic
option, so for a long time it stamped none of them -- while
`bench/ad6_i2_measure.py` made all three selectable AND stamped them. The
result was that a wl_stanford wall-clock could be quoted beside a wl_i2 one
with nothing in either file recording that the first is Minisat22 + the general
acyclic encoding and the second typically Cadical195 + the lite one.

These tests cover the half that is now fixed (what actually ran is recorded)
and deliberately NOT the half that is still open (making those choices
selectable here). They run no model build: `_config_stamp` is pure, which is
why it was lifted out of `measure()`.
"""

import unittest

from bench.ad6_faithful_measure import _config_stamp
from bench.ad6_i2_measure import _SOLVERS
from bench.ad6_stamp import admission_stamp


class TestStanfordConfigStamp(unittest.TestCase):

    def test_the_solver_is_stamped_even_though_it_is_not_selectable(self):
        """ A hardcoded value is exactly the case that needs a stamp: nothing
        in the result file would otherwise say which backend produced it, and
        the reader has no flag to consult either. """
        for flow_path in (False, True):
            self.assertEqual(_config_stamp(flow_path)["solver"], "minisat22")

    def test_the_solver_name_matches_the_i2_drivers_vocabulary(self):
        """ The stamps exist so two result files can be COMPARED. If wl_i2's
        driver renamed its backend, a wl_stanford file saying "minisat22" would
        silently stop lining up with it -- so pin the spelling across the two
        rather than in one place. """
        self.assertIn(_config_stamp(False)["solver"], _SOLVERS)

    def test_the_grounding_tracks_the_flow_path_switch(self):
        """ Derived rather than stored separately, because `--flow-path`
        REPLACES the rank encoding -- two independent fields could disagree. """
        self.assertEqual(_config_stamp(False)["grounding"], "rank")
        self.assertEqual(_config_stamp(True)["grounding"], "flow")

    def test_the_session_shape_is_not_an_independent_knob(self):
        """ Generality-debt item 8: the flow constraint names its endpoints, so
        choosing it CHOOSES a fresh solver per query and choosing rank chooses
        the persistent session. A run that stamped `grounding: flow` with
        `fresh_per_query: false` would be describing an architecture that
        cannot exist. """
        rank, flow = _config_stamp(False), _config_stamp(True)
        self.assertFalse(rank["fresh_per_query"])
        self.assertFalse(rank["skip_acyclic"])
        self.assertTrue(flow["fresh_per_query"])
        self.assertTrue(flow["skip_acyclic"],
                        "the flow constraint replaces the rank encoding rather "
                        "than supplementing it")

    def test_the_acyclic_encoding_is_stamped_as_the_general_one(self):
        """ THE cross-benchmark field. wl_i2 cannot run this path at all (it
        OOMs) and uses `--lite-acyclic`; clause-identical by test, but a
        different code path, and the reader of a side-by-side table has to be
        able to see which one each number came from. """
        for flow_path in (False, True):
            self.assertIs(_config_stamp(flow_path)["lite_acyclic"], False)

    def test_probe_untag_is_stamped_rather_than_assumed(self):
        """ Generality-debt item 4: a cross-engine PARITY choice, not a
        fidelity one, so it has to be restated wherever a number appears. """
        self.assertIs(_config_stamp(False)["probe_untag"], False)

    def test_every_stamped_field_is_json_serialisable_scalar(self):
        """ These land in an archived result file; a stray object would make
        the run fail only at its very end, after the expensive part. """
        for flow_path in (False, True):
            for key, value in _config_stamp(flow_path).items():
                self.assertIsInstance(value, (str, bool), key)


class TestSharedAdmissionStamp(unittest.TestCase):
    """ `admission_stamp` moved to `bench/ad6_stamp.py` so both drivers compute
    it by the IDENTICAL rule -- two implementations drifting apart would defeat
    the stamp more quietly than omitting it. """

    def test_both_drivers_use_the_same_implementation(self):
        from bench.ad6_i2_measure import _admission_stamp
        self.assertIs(_admission_stamp, admission_stamp)

    def test_a_port_scoped_relation_is_reported_as_such(self):
        stamp = admission_stamp(
            {"in_vlans": {"in.a": {"p1": {"10", "20"}}, "in.b": {"p2": {"30"}}}})
        self.assertTrue(stamp["in_admission_port_scoped"])
        self.assertEqual(stamp["in_admission_ports"], 2)
        self.assertEqual(stamp["in_admission_pairs"], 3)

    def test_a_plain_ir_is_not_reported_as_port_scoped(self):
        """ A model doing no VLAN admission at all must not read as carrying
        the stronger per-port model. """
        self.assertFalse(admission_stamp({})["in_admission_port_scoped"])


if __name__ == '__main__':
    unittest.main()
