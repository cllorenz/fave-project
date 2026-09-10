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

""" `bench/ad6_i2_measure.py`'s run-configuration layer -- the switches the
THREE-QUERY FAITHFUL EXPERIMENT needs (AD6_PLAN.md §5.5 "C3 REOPENED",
TODO.md item 1s).

WHY THIS FILE EXISTS AT ALL, given the script it covers cannot run here.
The experiment is a single ~20 GB, multi-hour, bare-metal run whose cheapest
failure mode is a typo: a misspelled router name that silently selects zero
queries, a `--probe-untag` that silently forces nothing, a result artifact
that does not record which of the three models produced it. None of those
would raise -- they would produce a plausible-looking JSON file after hours
of compute, and the only way to notice would be to run it again. So the
selection, validation and literal-resolution logic is factored out of
`measure()` into pure functions and pinned here, in the `fast` tier, where
it costs milliseconds. What is NOT covered here is the run itself (needs the
full native stack plus the memory envelope) -- that is the experiment, not a
test.

The three guards worth naming, because each one protects against a SILENT
wrong answer rather than a crash:

  * `_parse_pairs` rejects an unknown router name instead of yielding an
    empty query list. `--pair-filter` could only ever narrow a fixed 81-pair
    product, so it could not go wrong this way; a free-text pair list can.
  * `_forced_literals` rejects a variable name absent from the base
    encoding. This is the `IncrementalSession._index_for` hazard in the
    open: that method INVENTS a fresh, otherwise-unconstrained index for an
    unknown name, so a misaddressed untag literal would be satisfiable by
    construction and the untagged run would silently equal the untagless
    one. `ad6/test/parser/favemodeltest.py`'s
    `test_the_forced_variables_exist_in_the_base_encoding` makes the same
    check against a real encoding; this makes it a hard failure in the
    measurement path too.
  * `--probe-untag` without `--faithful-vlan` is refused. `probe_vlan_literals`
    returns [] unless the IR is faithful, so the combination is a no-op that
    LOOKS like the untagged configuration was measured.
"""

import os
import sys
import unittest
from unittest import mock

import bench.ad6_i2_measure

from bench.ad6_i2_measure import (
    _parse_pairs, _select_queries, _forced_literals, _oracle_diff, _is_full_sweep,
    _extract_witness, _build_ir, _admission_stamp, main
)


_SOURCES = ['source.atla', 'source.chic', 'source.hous', 'source.salt', 'source.seat']
_PROBES = ['probe.atla', 'probe.chic', 'probe.hous', 'probe.salt', 'probe.seat']

# The experiment's own query set, AD6_PLAN.md §5.5 "C3 REOPENED": one
# agreement control plus the two pairs FaVe+NetPlumber calls unreachable.
_EXPERIMENT = "hous>salt,chic>salt,chic>seat"


class TestParsePairs(unittest.TestCase):
    """ `--pairs` parsing: the selector the experiment needs, which
    `--pair-filter` (self-only / exclude-self over the full product) cannot
    express. """

    def test_the_experiment_pair_set_parses_to_its_three_queries(self):
        self.assertEqual(_parse_pairs(_EXPERIMENT, _SOURCES, _PROBES), [
            {'source': 'source.hous', 'probe': 'probe.salt'},
            {'source': 'source.chic', 'probe': 'probe.salt'},
            {'source': 'source.chic', 'probe': 'probe.seat'},
        ])

    def test_order_is_as_written_not_sorted(self):
        """ The control (`hous->salt`, a pair both engines call reachable) is
        deliberately FIRST: it is the cheapest recorded query at 1.11 s, so
        it fails fast if the faithful encoding is broken outright, before
        either discriminator's unknown-cost UNSAT is attempted. Sorting the
        list would put a discriminator first and lose that. """
        parsed = _parse_pairs("seat>atla,atla>seat", _SOURCES, _PROBES)
        self.assertEqual([q['source'] for q in parsed], ['source.seat', 'source.atla'])

    def test_fully_qualified_names_are_accepted_too(self):
        self.assertEqual(
            _parse_pairs("source.chic>probe.salt", _SOURCES, _PROBES),
            [{'source': 'source.chic', 'probe': 'probe.salt'}])

    def test_surrounding_whitespace_is_tolerated(self):
        self.assertEqual(
            _parse_pairs(" chic > salt , chic>seat ", _SOURCES, _PROBES),
            [{'source': 'source.chic', 'probe': 'probe.salt'},
             {'source': 'source.chic', 'probe': 'probe.seat'}])

    def test_an_unknown_source_is_rejected_and_named(self):
        """ The whole point of the guard: `chi` is not `chic`, and a typo
        that merely selected nothing would waste the entire run. """
        with self.assertRaises(ValueError) as ctx:
            _parse_pairs("chi>salt", _SOURCES, _PROBES)
        self.assertIn('chi', str(ctx.exception))
        self.assertIn('source', str(ctx.exception))

    def test_an_unknown_probe_is_rejected_and_named(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_pairs("chic>seatle", _SOURCES, _PROBES)
        self.assertIn('seatle', str(ctx.exception))
        self.assertIn('probe', str(ctx.exception))

    def test_the_error_lists_the_available_names(self):
        """ A rejected run should be repairable from its own message, without
        going back to the model to look up what the routers are called. """
        with self.assertRaises(ValueError) as ctx:
            _parse_pairs("nope>salt", _SOURCES, _PROBES)
        self.assertIn('chic', str(ctx.exception))

    def test_a_missing_separator_is_rejected(self):
        with self.assertRaises(ValueError):
            _parse_pairs("chic salt", _SOURCES, _PROBES)

    def test_an_empty_spec_is_rejected(self):
        """ Not "run everything": an empty `--pairs` is a mistake, and the
        default (no `--pairs` at all) already means everything. """
        with self.assertRaises(ValueError):
            _parse_pairs("", _SOURCES, _PROBES)

    def test_a_trailing_comma_is_rejected_rather_than_ignored(self):
        with self.assertRaises(ValueError):
            _parse_pairs("chic>salt,", _SOURCES, _PROBES)

    def test_a_self_pair_is_allowed(self):
        """ Not the experiment's shape, but legal -- the self pairs are real
        queries (`--pair-filter self-only` runs exactly them). """
        self.assertEqual(_parse_pairs("chic>chic", _SOURCES, _PROBES),
                         [{'source': 'source.chic', 'probe': 'probe.chic'}])


class TestSelectQueries(unittest.TestCase):
    """ Query selection as a whole -- including that adding `--pairs` did not
    disturb the default and `--pair-filter` paths every recorded run so far
    was produced with. """

    def test_the_default_is_the_full_product_in_the_recorded_order(self):
        """ Probe-outer, source-inner: the order every archived `query_log`
        was written in, so `index` stays comparable across runs. """
        queries = _select_queries(_SOURCES, _PROBES)
        self.assertEqual(len(queries), 25)
        self.assertEqual(queries[0], {'source': 'source.atla', 'probe': 'probe.atla'})
        self.assertEqual(queries[1], {'source': 'source.chic', 'probe': 'probe.atla'})

    def test_self_only_is_unchanged(self):
        queries = _select_queries(_SOURCES, _PROBES, pair_filter='self-only')
        self.assertEqual(len(queries), 5)
        self.assertTrue(all(q['source'].split('.')[1] == q['probe'].split('.')[1]
                            for q in queries))

    def test_exclude_self_is_unchanged(self):
        queries = _select_queries(_SOURCES, _PROBES, pair_filter='exclude-self')
        self.assertEqual(len(queries), 20)
        self.assertTrue(all(q['source'].split('.')[1] != q['probe'].split('.')[1]
                            for q in queries))

    def test_max_queries_still_truncates(self):
        self.assertEqual(len(_select_queries(_SOURCES, _PROBES, max_queries=3)), 3)

    def test_pairs_selects_exactly_those_queries(self):
        self.assertEqual(_select_queries(_SOURCES, _PROBES, pairs=_EXPERIMENT), [
            {'source': 'source.hous', 'probe': 'probe.salt'},
            {'source': 'source.chic', 'probe': 'probe.salt'},
            {'source': 'source.chic', 'probe': 'probe.seat'},
        ])

    def test_pairs_and_pair_filter_together_are_refused(self):
        """ They mean contradictory things and one would silently win. """
        with self.assertRaises(ValueError):
            _select_queries(_SOURCES, _PROBES, pair_filter='exclude-self', pairs=_EXPERIMENT)

    def test_max_queries_still_applies_on_top_of_pairs(self):
        """ Deliberate: `--pairs <all three> --max-queries 1` is the cheap
        control-only probe that proves the faithful model builds and solves
        before the discriminators' unknown-cost UNSAT is committed to. """
        self.assertEqual(_select_queries(_SOURCES, _PROBES, pairs=_EXPERIMENT, max_queries=1),
                         [{'source': 'source.hous', 'probe': 'probe.salt'}])


class TestForcedLiterals(unittest.TestCase):
    """ The non-vacuity guard on query-time forced literals (the probe
    untag). """

    def setUp(self):
        self.name_to_index = {'vlan#probe_fanout_probe_salt_0': 7,
                              'vlan#probe_fanout_probe_salt_1': 8}

    def test_a_present_name_resolves_to_its_index(self):
        self.assertEqual(
            _forced_literals([('vlan#probe_fanout_probe_salt_0', False)],
                             self.name_to_index, 'probe untag'),
            [7])

    def test_a_negated_variable_resolves_to_a_negative_literal(self):
        """ vlan=0 is all-zero bits, so EVERY literal of the i2 untag is
        negated -- getting the sign wrong would force vlan=4095 instead. """
        self.assertEqual(
            _forced_literals([('vlan#probe_fanout_probe_salt_0', True),
                              ('vlan#probe_fanout_probe_salt_1', True)],
                             self.name_to_index, 'probe untag'),
            [-7, -8])

    def test_no_variables_resolve_to_no_literals(self):
        self.assertEqual(_forced_literals([], self.name_to_index, 'probe untag'), [])

    def test_a_name_absent_from_the_base_encoding_is_a_hard_failure(self):
        """ THE guard. `IncrementalSession._index_for` would instead invent a
        fresh unconstrained index, making the forced literal trivially
        satisfiable -- an untagged run that silently answers the untagless
        question. """
        with self.assertRaises(RuntimeError) as ctx:
            _forced_literals([('vlan#typo_node_0', False)], self.name_to_index, 'probe untag')
        self.assertIn('vlan#typo_node_0', str(ctx.exception))

    def test_the_failure_names_its_context(self):
        with self.assertRaises(RuntimeError) as ctx:
            _forced_literals([('vlan#typo_node_0', False)],
                             self.name_to_index, 'probe untag for probe.salt')
        self.assertIn('probe.salt', str(ctx.exception))

    def test_one_absent_name_among_present_ones_still_fails(self):
        """ Partial resolution is the dangerous case: 11 of 12 bits forced
        would still constrain the run, just not to the value asked for. """
        with self.assertRaises(RuntimeError):
            _forced_literals([('vlan#probe_fanout_probe_salt_0', True),
                              ('vlan#typo_node_1', True)],
                             self.name_to_index, 'probe untag')


class TestBuildIrFlags(unittest.TestCase):
    """ `_build_ir` hardcoded `faithful_vlan=False`; the experiment needs both
    it and `probe_untag` to reach `Ad6Adapter`. """

    def _capture(self, **kwargs):
        with mock.patch('ad6.adapter.Ad6Adapter') as adapter, \
             mock.patch('util.in_process_driver.InProcessFaVe'):
            _build_ir(**kwargs)
        return adapter.call_args

    def test_the_default_is_still_plain_mode(self):
        """ Every recorded i2 artifact is `faithful_vlan: false`; the default
        must keep reproducing them. """
        _, kwargs = self._capture()
        self.assertFalse(kwargs['faithful_vlan'])
        self.assertFalse(kwargs['probe_untag'])

    def test_faithful_vlan_reaches_the_adapter(self):
        _, kwargs = self._capture(faithful_vlan=True)
        self.assertTrue(kwargs['faithful_vlan'])
        self.assertFalse(kwargs['probe_untag'])

    def test_probe_untag_reaches_the_adapter(self):
        _, kwargs = self._capture(faithful_vlan=True, probe_untag=True)
        self.assertTrue(kwargs['faithful_vlan'])
        self.assertTrue(kwargs['probe_untag'])


class TestCli(unittest.TestCase):
    """ The command line the experiment is actually driven by. """

    def _measure_kwargs(self, argv):
        with mock.patch('bench.ad6_i2_measure.measure') as measure:
            main(argv)
        return measure.call_args[1]

    def test_defaults_are_unchanged(self):
        kwargs = self._measure_kwargs([])
        self.assertFalse(kwargs['faithful_vlan'])
        self.assertFalse(kwargs['probe_untag'])
        self.assertIsNone(kwargs['pairs'])
        self.assertFalse(kwargs['dry_run'])

    def test_faithful_vlan_flag(self):
        self.assertTrue(self._measure_kwargs(['--faithful-vlan'])['faithful_vlan'])

    def test_probe_untag_requires_faithful_vlan(self):
        """ Refused rather than silently ineffective: `probe_vlan_literals`
        returns [] on a plain IR, so this combination would report itself as
        an untag run while measuring the untagless model. """
        with self.assertRaises(SystemExit):
            self._measure_kwargs(['--probe-untag'])

    def test_probe_untag_with_faithful_vlan_is_accepted(self):
        kwargs = self._measure_kwargs(['--faithful-vlan', '--probe-untag'])
        self.assertTrue(kwargs['faithful_vlan'])
        self.assertTrue(kwargs['probe_untag'])

    def test_pairs_is_passed_through_verbatim(self):
        """ Parsing happens against the real source/probe names, which only
        exist after the IR is built. """
        self.assertEqual(self._measure_kwargs(['--pairs', _EXPERIMENT])['pairs'], _EXPERIMENT)

    def test_dry_run_flag(self):
        self.assertTrue(self._measure_kwargs(['--dry-run'])['dry_run'])

    def test_the_full_experiment_command_line_is_accepted(self):
        """ The untag-OFF run, exactly as AD6_PLAN.md §5.5 prescribes it:
        faithful, untag off, the three pairs, per-query checkpoints.

        `--lite-acyclic` is part of the recipe and not an optimisation:
        the general `_CreateAcyclicConstraints` does not complete on i2 (one
        giant SCC over 99.3% of nodes), the lite path emits the identical
        clause set, and all four recorded i2 artifacts carry
        `lite_acyclic: true` -- so it is also what keeps a faithful run
        comparable with the plain figures. """
        kwargs = self._measure_kwargs([
            '--faithful-vlan', '--lite-acyclic', '--pairs', _EXPERIMENT,
            '--solver', 'cadical195', '--checkpoint-every', '1',
            '--out', 'i2_faithful_untag_off.json'])
        self.assertTrue(kwargs['faithful_vlan'])
        self.assertFalse(kwargs['probe_untag'])
        self.assertTrue(kwargs['lite_acyclic'])
        self.assertEqual(kwargs['pairs'], _EXPERIMENT)
        self.assertEqual(kwargs['solver_name'], 'cadical195')
        self.assertEqual(kwargs['checkpoint_every'], 1)


if __name__ == '__main__':
    unittest.main()


class TestOracleDiff(unittest.TestCase):
    """ The oracle differential must be SCOPED to the pairs actually queried.

    Found by archiving the first real three-query result: the diff ran
    unconditionally against `reachable.json`'s full 72-pair mesh, so the 69
    pairs the run never asked about counted as unreachable and the artifact
    came out stamped `oracle_match: false`. That reads like ad6 failed the
    differential when in fact it answered three questions and got all three
    consistent with the oracle -- exactly the silent misreading the result
    stamping elsewhere in this script exists to prevent, and worse than a
    crash because the file outlives the run that explains it. """

    ORACLE = {'salt': ['chic', 'hous', 'atla'], 'seat': ['chic'], 'atla': ['hous']}

    def test_a_full_run_that_agrees_matches(self):
        reach = {'salt': ['chic', 'hous', 'atla'], 'seat': ['chic'], 'atla': ['hous']}
        d = _oracle_diff(reach, self.ORACLE, None)
        self.assertTrue(d['oracle_match'])
        self.assertEqual(d['oracle_missing'], {})
        self.assertEqual(d['oracle_extra'], {})

    def test_a_full_run_that_underapproximates_does_not_match(self):
        reach = {'salt': ['chic'], 'seat': ['chic'], 'atla': ['hous']}
        d = _oracle_diff(reach, self.ORACLE, None)
        self.assertFalse(d['oracle_match'])
        self.assertEqual(d['oracle_missing'], {'salt': ['atla', 'hous']})

    def test_a_full_run_that_overapproximates_does_not_match(self):
        reach = {'salt': ['chic', 'hous', 'atla'], 'seat': ['chic', 'kans'], 'atla': ['hous']}
        d = _oracle_diff(reach, self.ORACLE, None)
        self.assertFalse(d['oracle_match'])
        self.assertEqual(d['oracle_extra'], {'seat': ['kans']})

    def test_a_scoped_run_ignores_pairs_it_never_queried(self):
        """ THE fix. Three queries, all agreeing with the oracle -- the 69
        unasked pairs must not be read as unreachable. """
        queried = [('source.hous', 'probe.salt'), ('source.chic', 'probe.salt'),
                   ('source.chic', 'probe.seat')]
        reach = {'salt': ['chic', 'hous'], 'seat': ['chic'], 'atla': []}
        d = _oracle_diff(reach, self.ORACLE, queried)
        self.assertTrue(d['oracle_match'])
        self.assertEqual(d['oracle_pairs_compared'], 3)

    def test_a_scoped_run_still_catches_a_real_disagreement(self):
        """ Scoping must not become a way of never failing: within the pairs
        actually queried, a divergence still has to surface. """
        queried = [('source.hous', 'probe.salt'), ('source.chic', 'probe.seat')]
        reach = {'salt': [], 'seat': ['chic'], 'atla': []}
        d = _oracle_diff(reach, self.ORACLE, queried)
        self.assertFalse(d['oracle_match'])
        self.assertEqual(d['oracle_missing'], {'salt': ['hous']})

    def test_a_scoped_run_records_its_own_scope(self):
        """ The artifact has to say the verdict is partial, so a future reader
        cannot mistake a 3-pair agreement for the full 72-pair differential. """
        queried = [('source.chic', 'probe.seat')]
        d = _oracle_diff({'seat': ['chic']}, self.ORACLE, queried)
        self.assertEqual(d['oracle_pairs_compared'], 1)
        self.assertFalse(d['oracle_full_set'])

    def test_a_full_run_records_that_it_was_full(self):
        reach = {'salt': ['chic', 'hous', 'atla'], 'seat': ['chic'], 'atla': ['hous']}
        d = _oracle_diff(reach, self.ORACLE, None)
        self.assertTrue(d['oracle_full_set'])

    def test_a_self_pair_is_never_compared(self):
        """ `reach_matrix` excludes self pairs by construction, and the oracle
        has none either -- a queried self pair must not read as missing. """
        queried = [('source.salt', 'probe.salt')]
        d = _oracle_diff({'salt': []}, self.ORACLE, queried)
        self.assertTrue(d['oracle_match'])
        self.assertEqual(d['oracle_pairs_compared'], 0)


class TestIsFullSweep(unittest.TestCase):
    """ Whether the oracle differential is the full 72-pair question or a
    scoped one, decided from the queries answered rather than from the flags
    passed -- see `_is_full_sweep`. """

    def test_the_experiment_is_not_a_full_sweep(self):
        answered = [('source.hous', 'probe.salt'), ('source.chic', 'probe.salt'),
                    ('source.chic', 'probe.seat')]
        self.assertFalse(_is_full_sweep(answered, _SOURCES, _PROBES))

    def test_every_non_self_pair_is_a_full_sweep(self):
        answered = [(s, p) for p in _PROBES for s in _SOURCES]
        self.assertTrue(_is_full_sweep(answered, _SOURCES, _PROBES))

    def test_exclude_self_still_counts_as_a_full_sweep(self):
        """ The case a flag-based test would get wrong: `--pair-filter
        exclude-self` drops only pairs the differential never compares, so it
        answers the full question. """
        answered = [(s, p) for p in _PROBES for s in _SOURCES
                    if s.split('.')[1] != p.split('.')[1]]
        self.assertTrue(_is_full_sweep(answered, _SOURCES, _PROBES))

    def test_one_missing_pair_is_not_a_full_sweep(self):
        answered = [(s, p) for p in _PROBES for s in _SOURCES
                    if s.split('.')[1] != p.split('.')[1]][:-1]
        self.assertFalse(_is_full_sweep(answered, _SOURCES, _PROBES))

    def test_self_only_is_not_a_full_sweep(self):
        answered = [(s, p) for p in _PROBES for s in _SOURCES
                    if s.split('.')[1] == p.split('.')[1]]
        self.assertFalse(_is_full_sweep(answered, _SOURCES, _PROBES))


class TestWitnessCli(unittest.TestCase):
    """ `--witness`: extract the traversed FaVe devices from a SAT solve.

    The consumer of the shared primitive (AD6_PLAN.md §5.5 "ROOT-CAUSING
    PLAN"). Opt-in rather than always-on because it costs one pass over the
    instance's whole variable table to build the transition-name index, and
    every recorded run so far did not need it. """

    def _measure_kwargs(self, argv):
        with mock.patch('bench.ad6_i2_measure.measure') as measure:
            main(argv)
        return measure.call_args[1]

    def test_default_is_off(self):
        self.assertFalse(self._measure_kwargs([])['witness'])

    def test_the_flag_reaches_measure(self):
        self.assertTrue(self._measure_kwargs(['--witness'])['witness'])

    def test_it_composes_with_the_experiment_command_line(self):
        kwargs = self._measure_kwargs([
            '--faithful-vlan', '--lite-acyclic', '--witness',
            '--pairs', _EXPERIMENT, '--solver', 'cadical195'])
        self.assertTrue(kwargs['witness'])
        self.assertTrue(kwargs['faithful_vlan'])
        self.assertEqual(kwargs['pairs'], _EXPERIMENT)


class _StubSolver:
    def __init__(self, model):
        self._model = model

    def get_model(self):
        return self._model


class TestExtractWitness(unittest.TestCase):
    """ `_extract_witness` itself, not just its CLI flag.

    This class exists because the flag-plumbing tests above did NOT catch a
    plain `NameError` in this function: `favemodel` is imported INSIDE
    `measure()`, so it is a local of that function and a module-level helper
    cannot see it. The run died on the first SAT query after an 877 s build.
    Hence the module is now passed in explicitly -- which is both the fix and
    what makes the function injectable enough to test here for milliseconds
    instead of fifteen minutes. """

    _IR = {"devices": ["in.chic", "out.chic", "in.salt", "out.salt"],
           "generators": {"source.chic": None}, "probes": {"probe.salt": None}}

    def setUp(self):
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(
            bench.ad6_i2_measure.__file__)), '..', '..', 'ad6'))
        from src.parser import favemodel
        self.favemodel = favemodel
        self.source = favemodel.gen_entry_key('source.chic')
        self.dest = favemodel._probe_fanout_key('probe.salt')
        self.mid = 'fw_out_chic_fwd_r5'
        self.index_to_name = {
            1: '%s_true_%s' % (self.source, self.mid),
            2: '%s_true_%s' % (self.mid, self.dest),
            3: 'fw_in_salt_fwd_r0_true_fw_out_salt_fwd_r0',   # slack
        }

    def _extract(self, model, sat=True, witness=True):
        return _extract_witness(_StubSolver(model), sat, witness,
                                self.index_to_name, self.source, self.dest,
                                self._IR, self.favemodel)

    def test_witness_off_extracts_nothing(self):
        self.assertIsNone(self._extract([1, 2], witness=False))

    def test_unsat_extracts_nothing(self):
        """ UNSAT has no model; asking for one would be an error, not a
        witness. """
        self.assertIsNone(self._extract([1, 2], sat=False))

    def test_a_sat_solve_yields_the_device_walk(self):
        record = self._extract([1, 2])
        self.assertEqual(record['witness_devices'],
                         ['source.chic', 'out.chic', 'probe.salt'])
        self.assertEqual(record['witness_path_nodes'], 3)

    def test_the_edge_total_is_reported_alongside_the_walk(self):
        """ The slack indicator: 3 true edges but a 3-node walk using 2 of
        them. Without this a reader cannot tell how loose the model was. """
        record = self._extract([1, 2, 3])
        self.assertEqual(record['witness_edges_total'], 3)
        self.assertEqual(record['witness_devices'],
                         ['source.chic', 'out.chic', 'probe.salt'])

    def test_negative_literals_do_not_contribute_edges(self):
        record = self._extract([1, -2])
        self.assertEqual(record['witness_edges_total'], 1)
        self.assertIn('witness_error', record)

    def test_a_sat_solve_with_no_walk_reports_an_error_not_an_empty_path(self):
        """ SAT means the destination IS reachable, so no walk inside the
        true-edge set is a fact about extraction, not about reachability --
        it must not be reported as a zero-hop path. """
        record = self._extract([3])
        self.assertIn('witness_error', record)
        self.assertNotIn('witness_devices', record)

    def test_a_solver_returning_no_model_is_reported(self):
        record = _extract_witness(_StubSolver(None), True, True,
                                  self.index_to_name, self.source, self.dest,
                                  self._IR, self.favemodel)
        self.assertIn('witness_error', record)


class TestAdmissionStamp(unittest.TestCase):
    """ AD6_PLAN.md §5.5: `faithful_vlan: true` alone no longer identifies the
    encoding, so the result file has to say which ADMISSION model produced it.

    Before 2026-09-10 `ir["in_vlans"]` was a per-DEVICE VLAN set; it is now
    the per-(port, VLAN) relation, and on i2 the two give different
    reachability -- the pre-fix model admitted 2,555 of the 2,564
    route-crossings a real per-port configuration rejects. Both stamp
    `faithful_vlan: true` and `probe_untag: false`, so without this stamp the
    pre-fix `eval/ad6_i2_faithful_untagoff_3pairs_sandbox.json` and a post-fix
    run of the IDENTICAL command are distinguishable only by `kripke_nodes`
    (78,078 vs 78,524) -- derivable, but implicit. """

    def test_the_relation_is_reported_as_port_scoped_with_its_sizes(self):
        ir = {"in_vlans": {
            "in.a": {"1": ["10", "20"], "2": ["30"]},
            "in.b": {"5": ["40"]},
        }}
        self.assertEqual(_admission_stamp(ir), {
            "in_admission_port_scoped": True,
            "in_admission_ports": 3,
            "in_admission_pairs": 4,
        })

    def test_the_pre_fix_flat_shape_is_reported_as_not_port_scoped(self):
        """ favemodel._in_vlans_for still BUILDS this shape as the device-wide
        gate (so an archived IR reproduces its encoding), so a result carrying
        it must not claim the stronger model. """
        stamp = _admission_stamp({"in_vlans": {"in.a": ["10", "20"]}})
        self.assertFalse(stamp["in_admission_port_scoped"])
        self.assertEqual(stamp["in_admission_ports"], 0)
        self.assertEqual(stamp["in_admission_pairs"], 0)

    def test_a_mixed_ir_is_not_reported_as_port_scoped(self):
        """ Fail closed: a partially-migrated IR must read as NOT port-scoped
        rather than quietly claiming the stronger model for the whole run. """
        ir = {"in_vlans": {"in.a": {"1": ["10"]}, "in.b": ["20"]}}
        self.assertFalse(_admission_stamp(ir)["in_admission_port_scoped"])

    def test_a_plain_ir_is_not_reported_as_port_scoped(self):
        """ A plain IR has no `in_vlans` at all and does no VLAN admission
        whatsoever -- "port-scoped" would be actively misleading there, not
        merely absent. """
        for ir in ({}, {"in_vlans": {}}, {"in_vlans": None}):
            self.assertEqual(_admission_stamp(ir), {
                "in_admission_port_scoped": False,
                "in_admission_ports": 0,
                "in_admission_pairs": 0,
            }, ir)
