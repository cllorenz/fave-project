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

""" `test/i2_oracle.py` distinguishes a benign tightening of the plain wl_i2
model from an unsound one -- pinned here on synthetic sets, no engine needed.

This exists because the first version of the wl_i2 gate rewrite asserted
"soundness AND the surplus is exactly the 11 pairs" and believed that pinned the
relaxation. It does not: while the model reaches every pair, both follow
algebraically from that, so the assertions held for ANY oracle -- which is the
same shape of empty gate the rewrite was meant to remove. The vacuity case below
is that discovery, frozen.
"""

import unittest

from test.i2_oracle import plain_model_violations

# A miniature stand-in for wl_i2's 9 roles: every ordered pair, self excluded.
_ROLES = ('a', 'b', 'c', 'd')
_ALL = {(s, p) for s in _ROLES for p in _ROLES if s != p}
# Two of them are VLAN-blocked in the real data plane.
_UNREACHABLE = {('a', 'b'), ('c', 'd')}
_TRULY_REACHABLE = _ALL - _UNREACHABLE


class TestPlainModelClassification(unittest.TestCase):

    def test_the_documented_behaviour_passes(self):
        self.assertEqual(plain_model_violations(_ALL, _ALL, _UNREACHABLE), [])

    def test_losing_a_deliverable_pair_is_reported_as_unsound(self):
        got = _ALL - {('a', 'c')}          # ('a','c') is delivered for real
        violations = plain_model_violations(got, _ALL, _UNREACHABLE)
        self.assertTrue(any("UNSOUND" in v for v in violations), violations)

    def test_shedding_a_blocked_pair_is_drift_but_NOT_unsound(self):
        """ The attribution that `reachable.json` could not make: a model that
        tightened towards the data plane is not the same event as one that lost
        something deliverable, and must not read like it. """
        got = _ALL - {('a', 'b')}          # one of the VLAN-blocked pairs
        violations = plain_model_violations(got, _ALL, _UNREACHABLE)
        self.assertTrue(violations)
        self.assertFalse([v for v in violations if "UNSOUND" in v], violations)

    def test_tightening_all_the_way_is_drift_but_NOT_unsound(self):
        violations = plain_model_violations(_TRULY_REACHABLE, _ALL, _UNREACHABLE)
        self.assertTrue(violations)
        self.assertFalse([v for v in violations if "UNSOUND" in v], violations)

    def test_the_oracle_alone_cannot_falsify_a_model_that_reaches_everything(self):
        """ THE VACUITY CASE. Perturb the oracle, leave the model reaching all
        pairs: nothing fails. Soundness and the surplus are tautologies there, so
        these gates buy attribution, not detection power -- and any future claim
        that they pin the relaxation has to reckon with this test. """
        for perturbed in ({('a', 'b')}, {('c', 'd')}, set(), {('b', 'a')}):
            with self.subTest(oracle=sorted(perturbed)):
                self.assertEqual(plain_model_violations(_ALL, _ALL, perturbed), [])


if __name__ == '__main__':
    unittest.main()
