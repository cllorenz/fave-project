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
import unittest

from aggregator.aggregator_service import (
    BACKENDS, BACKEND_AD6, BACKEND_APKEEP, BACKEND_NETPLUMBER, build_engine,
)


_LOG = logging.getLogger("test_aggregator_backend")
_LOG.setLevel(logging.CRITICAL)


class TestBackendVocabulary(unittest.TestCase):

    def test_the_default_backend_is_netplumber(self):
        """ Back-compatibility is not optional here: every benchmark, script
        and CI job invokes the aggregator without naming a backend. """
        self.assertEqual(BACKENDS[0], BACKEND_NETPLUMBER)

    def test_all_three_engines_are_reachable(self):
        self.assertEqual(
            set(BACKENDS), {BACKEND_NETPLUMBER, BACKEND_APKEEP, BACKEND_AD6})

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
            {"translation": "literal", "grounding": "rank",
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
