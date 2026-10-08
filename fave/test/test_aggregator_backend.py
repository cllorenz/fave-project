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

""" AD6_PLAN.md §9.3 Phase 6: BACKEND SELECTION in the aggregator.

Until now `AggregatorService.__init__` hardcoded `NetPlumberAdapter`, and its
`engine=` parameter is documented as -- and is -- a TEST injection seam. So
although three verification engines exist in this tree (NetPlumber, APKeep/NDD,
ad6), **there was no production route to any but the first**: the only way to
run FaVe on ad6 was to construct the service from Python and inject the engine,
which no benchmark or script does.

That is the gap this closes. `--backend` picks the engine; the ad6 options that
are measurement-affecting (`--grounding`, `--solver`, `--lite-acyclic`) are
selectable alongside it, because a production path that can only run ONE
configuration cannot reproduce the numbers the measurement drivers produced --
and those drivers were deleted at §9.25.

These tests build engines, not models: no backend process, no JVM, no bridge
subprocess, so they run in the `fast` tier.
"""

import logging
import sys
import types
import unittest

from unittest import mock

from aggregator.aggregator_service import (
    BACKENDS, BACKEND_AD6, BACKEND_APKEEP, BACKEND_NETPLUMBER, BACKEND_VERIFLOW,
    BACKENDS_NEEDING_NETPLUMBER, BACKENDS_WITH_ANOMALIES, build_engine,
)


_LOG = logging.getLogger("test_aggregator_backend")
_LOG.setLevel(logging.CRITICAL)


class TestBackendVocabulary(unittest.TestCase):

    def test_the_default_backend_is_netplumber(self):
        """ Back-compatibility is not optional here: every benchmark, script
        and CI job invokes the aggregator without naming a backend. """
        self.assertEqual(BACKENDS[0], BACKEND_NETPLUMBER)

    def test_all_four_engines_are_reachable(self):
        self.assertEqual(
            set(BACKENDS),
            {BACKEND_NETPLUMBER, BACKEND_APKEEP, BACKEND_AD6, BACKEND_VERIFLOW})

    def test_veriflow_needs_no_net_plumber_and_checks_no_anomalies(self):
        """ It runs in-process (libveriflow_fr), and its Ch. 4 anomaly-like
        queries are not FaVe's anomaly step: a benchmark must skip that step
        rather than report a clean verdict for it. """
        self.assertNotIn(BACKEND_VERIFLOW, BACKENDS_NEEDING_NETPLUMBER)
        self.assertNotIn(BACKEND_VERIFLOW, BACKENDS_WITH_ANOMALIES)

    def test_an_unknown_backend_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            build_engine('netplumer', _LOG)          # sic
        self.assertIn('netplumer', str(caught.exception))


class TestBackendConstruction(unittest.TestCase):

    def test_netplumber_is_built_with_its_sockets(self):
        """ The one engine that needs transport. Passing no sockets is legal
        (the adapter tolerates an empty list); what matters is that they are
        threaded through rather than dropped. """
        engine = build_engine(BACKEND_NETPLUMBER, _LOG, socks=[],
                              asyncore_socks={}, mapping=None)
        self.assertEqual(type(engine).__name__, 'NetPlumberAdapter')

    def test_ad6_is_built_without_any_transport(self):
        """ ad6 runs as a subprocess per check_compliance, so it needs no
        sockets at all -- which is precisely why `main()` must not insist on
        connecting to net_plumber before starting under this backend. """
        engine = build_engine(BACKEND_AD6, _LOG)
        self.assertEqual(type(engine).__name__, 'Ad6Adapter')

    def test_the_ad6_options_reach_the_adapter(self):
        """ THE POINT OF PHASE 6's SECOND HALF. `bench/ad6_i2_measure.py` could
        select cadical195 and the lite acyclic encoding; the production path
        could not, so it could not reproduce a single archived wl_i2 number.
        Now it can, and the stamp says so. """
        engine = build_engine(BACKEND_AD6, _LOG, grounding='rank',
                              solver='cadical195', lite_acyclic=True)
        self.assertEqual(
            engine.configuration_stamp(),
            {"impl": "first-party",          # item 31, added 2026-10-02
             "translation": "literal", "grounding": "rank",
             "solver": "cadical195", "lite_acyclic": True})

    def test_a_bad_ad6_option_is_refused_at_construction(self):
        """ Not deferred into the bridge subprocess at the end of a model
        build. """
        with self.assertRaises(ValueError):
            build_engine(BACKEND_AD6, _LOG, solver='minisat')     # sic

    def test_ad6_options_are_ignored_by_the_other_backends(self):
        """ A shared factory must not make `--solver` look meaningful for
        NetPlumber. It is accepted and dropped rather than rejected, so one
        command line can switch backends without also editing away flags. """
        engine = build_engine(BACKEND_NETPLUMBER, _LOG, socks=[],
                              solver='cadical195', lite_acyclic=True)
        self.assertEqual(type(engine).__name__, 'NetPlumberAdapter')
        self.assertFalse(hasattr(engine, 'solver'))


class _RecordingAdapter:
    """ Stands in for APKeepAdapter so these stay fast-tier tests.

    The real adapter constructs LibAPKeep/LibNDD in `__init__`, which starts a
    JVM; what is under test here is which OPTIONS `build_engine` hands it, not
    what it then does with them. """

    def __init__(self, logger, mapping=None, faithful_vlan=None, engine=None):
        self.logger = logger
        self.mapping = mapping
        self.faithful_vlan = faithful_vlan
        self.engine = engine


def _build_apkeep(**kwargs):
    """ `build_engine` imports the adapter lazily, so a stub module in
    sys.modules is enough -- and keeps jpype out of the fast tier. """
    built = []

    def construct(*args, **options):
        built.append(_RecordingAdapter(*args, **options))
        return built[-1]

    stub = types.ModuleType("apkeep.adapter")
    stub.APKeepAdapter = construct
    with mock.patch.dict(sys.modules, {"apkeep.adapter": stub}):
        engine = build_engine(BACKEND_APKEEP, _LOG, **kwargs)
    # Return the recorder we built, having checked the factory returned it:
    # returning `engine` itself left pylint inferring the REAL adapters that
    # build_engine can return, none of which has these attributes.
    if len(built) != 1 or engine is not built[0]:
        raise AssertionError("build_engine did not return the one APKeep "
                             "adapter it constructed")
    return built[0]


class TestAPKeepDefaults(unittest.TestCase):
    """ Faithful VLAN handling is a PRIMARY objective, not an opt-in: ad6 and
    NetPlumber both model it, and an APKeep run that quietly drops it is not
    answering the same question. So the default is the faithful model, and the
    plain one has to be asked for.

    That forces the engine default too. The faithful model is exactly where
    BDD-APKeep's atomic-predicate cross-product explodes -- it does not finish
    wl_stanford or wl_i2 (APKEEP_NDD_EVAL.md §2.6/§2.6b) -- while the per-field
    NDD engine builds both in seconds. A faithful default on the BDD engine
    would be a default that cannot complete, so the two flips belong together. """

    def test_the_faithful_vlan_model_is_the_default(self):
        self.assertIs(_build_apkeep().faithful_vlan, True)

    def test_the_ndd_engine_is_the_default(self):
        self.assertEqual(_build_apkeep().engine, 'ndd')

    def test_the_plain_model_stays_selectable(self):
        """ Still needed: the P7a out-stage-collapse tests and the
        convergence harness measure the plain model deliberately. """
        self.assertIs(_build_apkeep(faithful_vlan=False).faithful_vlan, False)

    def test_the_bdd_engine_stays_selectable(self):
        """ The BDD engine is the comparand in every Sigma-vs-Pi result; it
        must remain reachable by name. """
        self.assertEqual(_build_apkeep(apkeep_engine='bdd').engine, 'bdd')


class TestAPKeepCommandLine(unittest.TestCase):
    """ The aggregator's own CLI, which is what a benchmark actually reaches
    through `FAVE_ENGINE_OPTIONS`. """

    def _parse(self, argv):
        from aggregator.aggregator_service import build_parser
        return build_parser().parse_args(argv)

    def test_the_faithful_model_is_on_without_any_flag(self):
        self.assertIs(self._parse([]).faithful_vlan, True)

    def test_no_vlan_turns_it_off(self):
        self.assertIs(self._parse(['--no-vlan']).faithful_vlan, False)

    def test_the_engine_defaults_to_ndd(self):
        self.assertEqual(self._parse([]).apkeep_engine, 'ndd')

    def test_the_bdd_engine_is_reachable_from_the_command_line(self):
        self.assertEqual(
            self._parse(['--apkeep-engine', 'bdd']).apkeep_engine, 'bdd')


class _RecordingVeriFlow:
    """ Stands in for VeriFlowAdapter, which needs the native engine built;
    what is under test is the OPTIONS build_engine hands it. """

    def __init__(self, logger, slicing=None, budget=None, revisit=None,
                 fields=None, invert_lpm=False):
        self.logger, self.slicing, self.budget = logger, slicing, budget
        self.revisit, self.fields = revisit, fields
        self.invert_lpm = invert_lpm


def _build_veriflow(**kwargs):
    """ As `_build_apkeep`: a stub module keeps the native engine out of the
    fast tier, and the recorder is returned -- checked to be what the factory
    returned -- so pylint does not infer the real adapters' attributes. """
    built = []

    def construct(*args, **options):
        built.append(_RecordingVeriFlow(*args, **options))
        return built[-1]

    stub = types.ModuleType("veriflow.adapter")
    stub.VeriFlowAdapter = construct
    with mock.patch.dict(sys.modules, {"veriflow.adapter": stub}):
        engine = build_engine(BACKEND_VERIFLOW, _LOG, **kwargs)
    if len(built) != 1 or engine is not built[0]:
        raise AssertionError("build_engine did not return the one VeriFlow-FR "
                             "adapter it constructed")
    return built[0]


class TestTheLpmGuardrailIsNotSilentlyIgnored(unittest.TestCase):
    """ MEASUREMENT_RUN_PLAN.md §5.4's guardrail, and the one backend option
    that must be REFUSED rather than ignored where it does not apply.

    `build_engine`'s rule is that backend-specific options are accepted and
    ignored by the backends they do not apply to, so one command line can
    switch engines. That rule is right for options that SELECT behaviour and
    wrong for this one. The guardrail reads "the verdict did not change under
    inversion" as "this check set cannot see longest-prefix-match"; on a
    backend that never applied the inversion the verdict cannot change for a
    reason that has nothing to do with the check set, so a silently-ignored
    flag manufactures the conclusion -- and the conclusion it manufactures is
    the one that retires the guardrail.
    """

    def test_netplumber_and_veriflow_take_it(self):
        self.assertTrue(_build_veriflow(invert_lpm=True).invert_lpm)
        engine = build_engine(BACKEND_NETPLUMBER, _LOG, invert_lpm=True)
        self.assertTrue(engine.invert_lpm)
        self.assertIs(engine.configuration_stamp()['np_invert_lpm'], True)

    def test_apkeep_and_ad6_REFUSE_it(self):
        for backend in (BACKEND_APKEEP, BACKEND_AD6):
            with self.subTest(backend=backend):
                with self.assertRaises(ValueError) as caught:
                    build_engine(backend, _LOG, invert_lpm=True)
                self.assertIn('--invert-lpm', str(caught.exception))
                self.assertIn(backend, str(caught.exception))

    def test_they_are_still_BUILDABLE_without_it(self):
        """ The refusal must be about the flag, not about the backend: a
        faithful apkeep or ad6 cell goes on working. """
        self.assertIsNotNone(build_engine(BACKEND_AD6, _LOG))
        self.assertFalse(
            build_engine(BACKEND_NETPLUMBER, _LOG).configuration_stamp()
            ['np_invert_lpm'])


class TestTheNoVlanGuardrailIsRefusedWhereItWouldDoNothing(unittest.TestCase):
    """ `--no-vlan` is the VLAN arm of the same guardrail, and it has the
    same failure mode as `--invert-lpm`: it relaxes a dimension, and
    relaxing can only ADD reachability, so an unchanged verdict is read as
    'this check set cannot see VLAN'. Only APKeep models VLAN behind a
    flag -- NetPlumber and VeriFlow-FR translate the model's rules
    literally, and ad6's semantic path (the one `faithful_vlan`
    configured) was deleted (`AD6_PLAN.md` §9.25). On any of those the arm
    would relax nothing, the verdict could not move, and the guardrail
    would manufacture its own conclusion.

    It was accepted-and-ignored until 2026-10-08, in the same function as
    the comment explaining why the LPM flag must not be. """

    def test_the_backends_without_the_flag_REFUSE_it(self):
        for backend in (BACKEND_NETPLUMBER, BACKEND_VERIFLOW, BACKEND_AD6):
            with self.subTest(backend=backend):
                with self.assertRaises(ValueError) as caught:
                    build_engine(backend, _LOG, faithful_vlan=False)
                self.assertIn('--no-vlan', str(caught.exception))
                self.assertIn(backend, str(caught.exception))

    def test_they_are_still_BUILDABLE_faithfully(self):
        # The refusal is about the flag, not the backend: the default arm
        # goes on working, which is every other cell in the campaign.
        for backend in (BACKEND_NETPLUMBER, BACKEND_VERIFLOW, BACKEND_AD6):
            with self.subTest(backend=backend):
                self.assertIsNotNone(build_engine(backend, _LOG))

    def test_the_default_is_faithful_so_nothing_has_to_ask(self):
        # `faithful_vlan=True` is the signature default; a caller that
        # never mentions VLAN must not trip a guardrail it did not invoke.
        self.assertIsNotNone(build_engine(BACKEND_NETPLUMBER, _LOG,
                                          faithful_vlan=True))

class TestVeriFlowDefaults(unittest.TestCase):
    """ VeriFlow-FR's measurement-affecting choices (VERIFLOW_PLAN.md §8):
    the defaults are the decided ones -- D6's 4+10 fields, Q4's state revisit,
    Q22's device-local slicing -- and no budget, since the suite's limit is
    external (TODO item 31). Each other value stays reachable by name. """

    def test_the_defaults_are_the_decided_ones(self):
        engine = _build_veriflow()
        self.assertEqual((engine.fields, engine.revisit, engine.slicing, engine.budget),
                         ("4+10", "state", "device", 0))

    def test_the_ablations_stay_selectable(self):
        engine = _build_veriflow(vf_fields="plain", vf_revisit="path",
                                 vf_slicing="network", vf_budget=1000)
        self.assertEqual((engine.fields, engine.revisit, engine.slicing, engine.budget),
                         ("plain", "path", "network", 1000))

    def test_veriflow_options_are_ignored_by_the_other_backends(self):
        engine = build_engine(BACKEND_NETPLUMBER, _LOG, socks=[], vf_fields="plain")
        self.assertEqual(type(engine).__name__, 'NetPlumberAdapter')


class TestVeriFlowCommandLine(unittest.TestCase):

    def _parse(self, argv):
        from aggregator.aggregator_service import build_parser
        return build_parser().parse_args(argv)

    def test_veriflow_is_a_backend_choice(self):
        self.assertEqual(self._parse(['-b', 'veriflow']).backend, BACKEND_VERIFLOW)

    def test_the_options_and_their_defaults(self):
        args = self._parse([])
        self.assertEqual((args.vf_fields, args.vf_revisit, args.vf_slicing, args.vf_budget),
                         ("4+10", "state", "device", 0))
        args = self._parse(['--vf-fields', 'plain', '--vf-revisit', 'path',
                            '--vf-slicing', 'network', '--vf-budget', '7'])
        self.assertEqual((args.vf_fields, args.vf_revisit, args.vf_slicing, args.vf_budget),
                         ("plain", "path", "network", 7))


class TestServiceWiring(unittest.TestCase):
    """ `engine=` must stay the TEST seam it is documented to be, and
    `backend=` must be the production route. """

    def _service(self, **kwargs):
        from aggregator.aggregator_service import AggregatorService
        from types import SimpleNamespace
        reporter = SimpleNamespace(daemon=False, start=lambda: None)
        return AggregatorService({}, {}, reporter=reporter, **kwargs)

    def test_the_service_defaults_to_netplumber(self):
        service = self._service()
        self.assertEqual(type(service.verification_engine).__name__,
                         'NetPlumberAdapter')

    def test_the_service_honours_the_backend_argument(self):
        service = self._service(backend=BACKEND_AD6)
        self.assertEqual(type(service.verification_engine).__name__,
                         'Ad6Adapter')

    def test_an_injected_engine_still_wins(self):
        """ The seam the tests rely on must survive: if both are given, the
        explicit object is used. """
        sentinel = object()
        service = self._service(engine=sentinel, backend=BACKEND_AD6)
        self.assertIs(service.verification_engine, sentinel)


if __name__ == '__main__':
    unittest.main()
