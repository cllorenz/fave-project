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

""" AD6_PLAN.md §9.3 Phase 6: the adapter's SOLVER and `lite_acyclic`
selectors, and the stamp that reports them.

Until Phase 6 the bridge hardcoded `Minisat22` and never reached
`_CreateAcyclicConstraintsLite` at all, so the production path could not
reproduce the cadical195 configuration every wl_i2 number was measured under,
and i2 through FaVe was possible only under flow grounding. The measurement
drivers could pick both and FaVe could not -- backwards, and the drivers were
deleted at §9.25, which would have taken the capability with them.

Structured like test_ad6_grounding.py's own constants/plumbing split: these
tests build no model and need no backend, so they run in the `fast` tier. The
end-to-end proof that a different backend answers the SAME question lives on
the ad6 side, where the solver is actually constructed
(`instantiatortest.py::IncrementalSessionSolverTest`).
"""

import logging
import os
import sys
import unittest

from ad6.adapter import (
    AD6_ROOT, GROUNDING_FLOW, GROUNDING_RANK, SOLVER_MINISAT22, SOLVERS,
    SOLVERS_WITHOUT_ASSUMPTIONS, Ad6Adapter,
)


def _adapter(**kwargs):
    log = logging.getLogger("test_ad6_solver")
    log.setLevel(logging.CRITICAL)
    return Ad6Adapter(log, **kwargs)


class TestSolverConstants(unittest.TestCase):
    """ `fave/ad6/adapter.py` DUPLICATES ad6's solver names rather than
    importing them -- it drives ad6 as a subprocess and deliberately imports
    nothing from the `ad6/` package. This is the guard that keeps the
    duplication from drifting, exactly as TestGroundingConstants does for
    GROUNDINGS: a backend added, renamed or removed in ad6 without updating the
    adapter would otherwise surface only as an argparse rejection inside a
    subprocess, at the end of a model build. """

    @staticmethod
    def _canonical():
        sys.path.insert(0, AD6_ROOT)
        try:
            from src.solver.incremental import (
                SOLVERS as CANONICAL, SOLVERS_WITHOUT_ASSUMPTIONS as CANONICAL_NA,
                SOLVER_MINISAT22 as CANONICAL_DEFAULT)
        finally:
            sys.path.remove(AD6_ROOT)
        return CANONICAL, CANONICAL_NA, CANONICAL_DEFAULT

    def test_the_fave_side_names_match_ad6s_canonical_definition(self):
        canonical, canonical_na, canonical_default = self._canonical()
        self.assertEqual(
            tuple(SOLVERS), tuple(canonical),
            "fave/ad6/adapter.py's SOLVERS has drifted from "
            "ad6/src/solver/incremental.py's -- the adapter would pass a name "
            "the bridge rejects (or silently omit a usable one)")
        self.assertEqual(SOLVER_MINISAT22, canonical_default)

    def test_the_no_assumptions_list_matches_too(self):
        """ Drift HERE is the dangerous direction: a backend that lands in
        ad6's list but not the adapter's would be accepted at construction and
        refused only in the subprocess -- and if it drifted the other way, a
        rank-grounded run on it reports EVERYTHING reachable without failing. """
        _canonical, canonical_na, _default = self._canonical()
        self.assertEqual(tuple(SOLVERS_WITHOUT_ASSUMPTIONS), tuple(canonical_na))

    def test_every_no_assumptions_solver_is_a_real_solver(self):
        for name in SOLVERS_WITHOUT_ASSUMPTIONS:
            self.assertIn(name, SOLVERS)


class TestSolverPlumbing(unittest.TestCase):
    """ The adapter's own contract, without building a model. """

    def test_the_default_solver_is_minisat22(self):
        """ Back-compatibility: every archived result came from it. """
        self.assertEqual(_adapter().solver, SOLVER_MINISAT22)

    def test_every_declared_solver_is_accepted(self):
        for name in SOLVERS:
            grounding = (GROUNDING_FLOW if name in SOLVERS_WITHOUT_ASSUMPTIONS
                         else GROUNDING_RANK)
            with self.subTest(solver=name):
                self.assertEqual(
                    _adapter(solver=name, grounding=grounding).solver, name)

    def test_an_unknown_solver_is_refused(self):
        """ Loudly, at construction -- before a model is built, not after. """
        with self.assertRaises(ValueError):
            _adapter(solver='minisat')          # sic: the PySAT name is minisat22

    def test_a_no_assumptions_solver_is_refused_under_rank(self):
        """ THE TRAP. Kissat404's PySAT wrapper silently ignores `assumptions`,
        which is how the rank grounding forces a query's endpoints -- so both
        would be dropped, every query would be solved against the bare base
        encoding, and the run would report EVERYTHING reachable without
        failing. Refused here as well as in the session so it costs nothing to
        find out. """
        with self.assertRaises(ValueError) as caught:
            _adapter(solver='kissat404', grounding=GROUNDING_RANK)
        message = str(caught.exception)
        self.assertIn('kissat404', message)
        self.assertIn(GROUNDING_FLOW, message,
                      "the refusal must name the grounding that DOES work")

    def test_the_same_solver_is_accepted_under_flow(self):
        """ It is the COMBINATION that is unusable, not the backend. """
        self.assertEqual(
            _adapter(solver='kissat404', grounding=GROUNDING_FLOW).solver,
            'kissat404')


class TestLiteAcyclicPlumbing(unittest.TestCase):

    def test_the_default_is_off(self):
        self.assertFalse(_adapter().lite_acyclic_applies)

    def test_it_applies_under_rank(self):
        self.assertTrue(
            _adapter(lite_acyclic=True, grounding=GROUNDING_RANK).lite_acyclic_applies)

    def test_it_does_NOT_apply_under_flow(self):
        """ The flow grounding builds no rank constraints, so the lite acyclic
        encoding cannot have been used. Reporting it as applied would mislabel
        the result -- the mistake §9.16.1 caught for `faithful_vlan`. """
        self.assertFalse(
            _adapter(lite_acyclic=True, grounding=GROUNDING_FLOW).lite_acyclic_applies)


class TestConfigurationStamp(unittest.TestCase):
    """ The generality-debt gate: every measurement-affecting choice is a
    stamped field. Phase 6 adds two, so the stamp has to carry them. """

    def test_the_stamp_carries_all_four_fields(self):
        self.assertEqual(
            _adapter(solver='cadical195', lite_acyclic=True).configuration_stamp(),
            {"translation": "literal", "grounding": "rank",
             "solver": "cadical195", "lite_acyclic": True})

    def test_the_stamp_reports_what_was_USED_not_what_was_asked_for(self):
        """ `lite_acyclic=True` under the flow grounding must stamp False: the
        encoding it names was never built. """
        stamp = _adapter(lite_acyclic=True,
                         grounding=GROUNDING_FLOW).configuration_stamp()
        self.assertFalse(stamp["lite_acyclic"])
        self.assertEqual(stamp["grounding"], GROUNDING_FLOW)


if __name__ == '__main__':
    unittest.main()
