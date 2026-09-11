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

Both halves are now closed: the choices are selectable (`--solver`,
`--lite-acyclic`, `--fresh-per-query`) and what actually ran is recorded. These
tests run no model build -- `_config_stamp` is pure, which is why it was lifted
out of `measure()`, and the CLI tests mock `measure` away.
"""

import io
import unittest
from unittest import mock

import bench.ad6_faithful_measure
from bench.ad6_faithful_measure import _config_stamp, main
from bench.ad6_i2_measure import _SOLVERS
from bench.ad6_stamp import (
    SOLVERS, SOLVERS_WITHOUT_ASSUMPTIONS, admission_stamp, needs_fresh_per_query,
    solver_class)


class TestStanfordConfigStamp(unittest.TestCase):

    def test_the_default_solver_is_what_the_archive_was_produced_under(self):
        """ Every archived wl_stanford result predates `--solver` and ran
        Minisat22, so that stays the default -- changing it would silently make
        new runs incomparable with the ones already in eval/. """
        for flow_path in (False, True):
            self.assertEqual(_config_stamp(flow_path)["solver"], "minisat22")

    def test_the_chosen_solver_is_what_gets_stamped(self):
        for name in SOLVERS:
            self.assertEqual(
                _config_stamp(False, solver_name=name)["solver"], name)

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
        self.assertIs(_config_stamp(False, fresh_per_query=True)["fresh_per_query"],
                      True, "and it is a free choice under the rank grounding")
        self.assertFalse(rank["fresh_per_query"])
        self.assertFalse(rank["skip_acyclic"])
        self.assertTrue(flow["fresh_per_query"])
        self.assertTrue(flow["skip_acyclic"],
                        "the flow constraint replaces the rank encoding rather "
                        "than supplementing it")

    def test_the_acyclic_encoding_is_stamped_as_chosen(self):
        """ THE cross-benchmark field. wl_i2 cannot run the general path at all
        (it OOMs) and is always lite; clause-identical by test, but a different
        code path, and the reader of a side-by-side table has to be able to see
        which one each number came from -- which is also why wl_stanford can
        now be pointed at the lite encoding to match it. """
        self.assertIs(_config_stamp(False)["lite_acyclic"], False)
        self.assertIs(_config_stamp(False, lite_acyclic=True)["lite_acyclic"], True)

    def test_lite_acyclic_is_not_stamped_under_the_flow_grounding(self):
        """ --flow-path builds NO rank constraints, so there is no encoding for
        lite-vs-general to describe. Stamping it true there would record an
        encoding the run never used. """
        self.assertIs(
            _config_stamp(True, lite_acyclic=True)["lite_acyclic"], False)

    def test_a_solver_that_ignores_assumptions_forces_fresh_per_query(self):
        """ Not a preference: under such a backend the persistent session drops
        each query's endpoint literals, so the stamp must never claim the
        persistent architecture for it. `measure()` forces the same thing, so
        the file cannot describe a run that is impossible. """
        for name in SOLVERS_WITHOUT_ASSUMPTIONS:
            self.assertTrue(needs_fresh_per_query(name))
            self.assertIs(
                _config_stamp(False, solver_name=name,
                              fresh_per_query=True)["fresh_per_query"], True)

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


class TestSolverRegistry(unittest.TestCase):
    """ The solver vocabulary is shared so a name means the same thing in both
    drivers' result files (`bench/ad6_stamp.py`). """

    def test_every_named_solver_resolves_to_a_pysat_class(self):
        """ An unresolvable name would fail only after the model build, i.e.
        minutes-to-hours into a run. """
        for name in SOLVERS:
            self.assertTrue(callable(solver_class(name)), name)

    def test_both_drivers_share_one_vocabulary(self):
        self.assertEqual(tuple(_SOLVERS), tuple(SOLVERS))

    def test_kissat_really_does_ignore_assumptions(self):
        """ THE premise the `--fresh-per-query` guard rests on, pinned as an
        experiment rather than quoted from documentation -- and the thing that
        makes it urgent: the wrong configuration does not fail, it returns SAT.

        Bootstrapped with the single clause (x1 OR x2) and solved under
        assumptions (-x1, -x2), a solver that honours assumptions must refute.
        If PySAT ever gains real assumption support for a backend listed in
        SOLVERS_WITHOUT_ASSUMPTIONS, this test fails and the guard can be
        relaxed -- which is the point of pinning it here. """
        for name in SOLVERS:
            cls = solver_class(name)
            solver = cls(bootstrap_with=[[1, 2]])
            try:
                self.assertTrue(solver.solve(), "%s: the clause is satisfiable" % name)
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    refuted = solver.solve(assumptions=[-1, -2]) is False
            finally:
                solver.delete()
            self.assertEqual(
                refuted, not needs_fresh_per_query(name),
                "%s: SOLVERS_WITHOUT_ASSUMPTIONS disagrees with the solver's "
                "actual behaviour -- the --fresh-per-query guard is now either "
                "missing or unnecessary for it" % name)


class TestFaithfulMeasureCli(unittest.TestCase):
    """ Both guards refuse rather than resolve: either resolution would produce
    a plausible-looking result file answering a different question than the
    flags claim. """

    def test_a_solver_ignoring_assumptions_is_refused_without_fresh_per_query(self):
        for name in SOLVERS_WITHOUT_ASSUMPTIONS:
            with self.assertRaises(SystemExit):
                with mock.patch('sys.stderr', new_callable=io.StringIO):
                    main(["--solver", name, "--out", "/dev/null"])

    def test_the_same_solver_is_accepted_with_fresh_per_query(self):
        for name in SOLVERS_WITHOUT_ASSUMPTIONS:
            with mock.patch.object(bench.ad6_faithful_measure, 'measure') as m:
                main(["--solver", name, "--fresh-per-query", "--out", "/dev/null"])
            self.assertEqual(m.call_args.kwargs["solver_name"], name)
            self.assertIs(m.call_args.kwargs["fresh_per_query"], True)

    def test_flow_path_also_satisfies_the_requirement(self):
        """ --flow-path already implies a fresh solver per query, so it must
        not be refused for a solver that needs one. """
        for name in SOLVERS_WITHOUT_ASSUMPTIONS:
            with mock.patch.object(bench.ad6_faithful_measure, 'measure') as m:
                main(["--solver", name, "--flow-path", "--out", "/dev/null"])
            self.assertIs(m.call_args.kwargs["flow_path"], True)

    def test_lite_acyclic_with_flow_path_is_refused(self):
        """ The flow REPLACES the rank encoding, so there would be no rank
        constraints for --lite-acyclic to build and the run would stamp an
        encoding it never used. """
        with self.assertRaises(SystemExit):
            with mock.patch('sys.stderr', new_callable=io.StringIO):
                main(["--lite-acyclic", "--flow-path", "--out", "/dev/null"])

    def test_the_defaults_reproduce_the_archived_configuration(self):
        """ A bare invocation must still be the Minisat22 + general-acyclic +
        persistent-session run every archived wl_stanford result came from. """
        with mock.patch.object(bench.ad6_faithful_measure, 'measure') as m:
            main(["--out", "/dev/null"])
        kw = m.call_args.kwargs
        self.assertEqual(kw["solver_name"], "minisat22")
        self.assertIs(kw["lite_acyclic"], False)
        self.assertIs(kw["fresh_per_query"], False)
        self.assertIs(kw["flow_path"], False)


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
