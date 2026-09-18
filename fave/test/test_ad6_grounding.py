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

""" The grounding strategy on the PRODUCTION path (AD6_PLAN.md §5.4 B1 / §5.5).

Two constraints close the SECRYPT'15 formalism's grounding gap
(`ad6/FAVE_CHANGES.md` §20 -- `trans(C)`'s support term is purely local, so a
floating cycle discharges it self-referentially and the paper's "a solution
represents a path starting at an initial state" does not hold):

  * the acyclic RANK encoding, baked into the shared base -- property-agnostic,
    and what every archived result was produced under;
  * a per-query single-unit s-t FLOW -- reachability-specific, and measured far
    cheaper at scale (wl_stanford N=16 faithful-VLAN, matched on cadical195:
    7.0x wall, 9.3x query, 1.4x peak RSS, for the identical 165-pair answer).

Until now the flow lived ONLY in the measurement drivers (deleted with the
semantic path at AD6_PLAN.md §9.25), which sat off the production path by design,
so nothing driven through FaVe could reach it. These tests cover the seam that
changed: the adapter's argument, the payload that carries it to the bridge, and
a real benchmark answering identically under both.
"""

import json
import logging
import os
import sys
import unittest
from unittest import mock

from ad6.adapter import (
    AD6_ROOT, GROUNDINGS, GROUNDING_FLOW, GROUNDING_RANK, Ad6Adapter, available)
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_ifi"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("topology.json", "routes.json", "sources.json", "policies.json",
            "reachable.json")]


def _inputs_present():
    return all(os.path.isfile(f) for f in _INPUTS)


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


class TestGroundingConstants(unittest.TestCase):
    """ `fave/ad6/adapter.py` DUPLICATES ad6's grounding names rather than
    importing them -- it drives ad6 as a subprocess and deliberately imports
    nothing from the `ad6/` package. This is the guard that keeps the
    duplication from drifting: a strategy added, renamed or removed in ad6
    without updating the adapter would otherwise only surface as an
    argparse `--grounding` rejection inside a subprocess, at the end of a
    model build. """

    def test_the_fave_side_names_match_ad6s_canonical_definition(self):
        sys.path.insert(0, AD6_ROOT)
        try:
            from src.solver.incremental import (
                GROUNDINGS as CANONICAL, GROUNDING_FLOW as CANONICAL_FLOW,
                GROUNDING_RANK as CANONICAL_RANK)
        finally:
            sys.path.remove(AD6_ROOT)
        self.assertEqual(
            tuple(GROUNDINGS), tuple(CANONICAL),
            "fave/ad6/adapter.py's GROUNDINGS has drifted from "
            "ad6/src/solver/incremental.py's -- the adapter would pass a name "
            "the bridge rejects (or silently omit a usable one)")
        self.assertEqual(GROUNDING_RANK, CANONICAL_RANK)
        self.assertEqual(GROUNDING_FLOW, CANONICAL_FLOW)


class TestGroundingPlumbing(unittest.TestCase):
    """ The adapter's own contract, without building a model. """

    def _adapter(self, **kwargs):
        log = logging.getLogger("test_ad6_grounding")
        log.setLevel(logging.WARNING)
        return Ad6Adapter(log, **kwargs)

    def test_the_default_is_rank(self):
        """ Deliberate, not incidental: the rank encoding is the only
        property-agnostic option, and every archived wl_ifi/wl_up/wl_tum/
        wl_stanford result was produced under it, so flipping the default
        would silently re-measure all of them. """
        self.assertEqual(self._adapter().grounding, GROUNDING_RANK)

    def test_an_unknown_grounding_is_refused_at_construction(self):
        """ Fail loudly and EARLY -- before a multi-hour model build, and
        before a result could be stamped with a strategy that never ran. """
        with self.assertRaises(ValueError):
            self._adapter(grounding='acyclic')

    def test_the_payload_carries_the_grounding_to_the_bridge(self):
        """ The adapter and the bridge are separate PROCESSES: the only thing
        connecting them is the JSON payload. A `grounding` the adapter accepts
        but never serialises would leave the bridge silently on its default --
        the exact failure this test exists to make impossible. """
        captured = {}

        def fake_run(argv, **_kwargs):
            captured['payload'] = json.load(open(argv[argv.index('--in') + 1]))
            with open(argv[argv.index('--out') + 1], 'w') as raw:
                json.dump([], raw)
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        for grounding in GROUNDINGS:
            engine = self._adapter(grounding=grounding)
            with mock.patch('ad6.adapter.subprocess.run', side_effect=fake_run):
                engine.check_compliance({})
            self.assertEqual(
                captured['payload'].get('grounding'), grounding,
                "the bridge would fall back to its own default")


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(_inputs_present(),
                 "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
class TestWlIfiUnderBothGroundings(unittest.TestCase):
    """ The end-to-end claim, on a real model rather than the synthetic
    floating-cycle fixture ad6's own suite uses: wl_ifi's full 17-role matrix
    through the real adapter/bridge/session must reproduce `reachable.json`
    EXACTLY under either grounding.

    This is what makes the flow strategy usable rather than merely present --
    the ad6-side unit tests prove it refuses the ungrounded pair, and this
    proves it does not refuse anything else on a genuine network. """

    @classmethod
    def _matrix(cls, grounding):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_grounding")
        log.setLevel(logging.WARNING)
        engine = Ad6Adapter(log, grounding=grounding)
        with InProcessFaVe(engine) as fave:
            fave.replay(_PREFIX)
            sources = sorted(engine._generators)
            probes = sorted(engine._probes)
            fave.check_compliance(
                {p: [[s, False, []] for s in sources] for p in probes})
        unreachable = {(s, p) for (s, p, _mr, _c)
                       in engine.get_compliance_results()}
        # Self-pairs KEPT -- see test_ad6_wl_ifi.py for why the
        # `_base(s) != _base(p)` filter that used to be here is now wrong:
        # wl_ifi's oracle asks `X -> X` since commit 7ec21124, and the switch
        # answers it locally.
        return {_base(p): set(_base(s) for s in sources
                              if (s, p) not in unreachable)
                for p in probes}

    @classmethod
    def setUpClass(cls):
        cls.expected = {r: set(v) for r, v
                        in json.load(open("%s/reachable.json" % _PREFIX)).items()}
        cls.matrices = {g: cls._matrix(g) for g in GROUNDINGS}

    def _assert_matches_oracle(self, grounding):
        got = self.matrices[grounding]
        diffs = {r: {"missing": sorted(self.expected.get(r, set()) - got.get(r, set())),
                     "extra": sorted(got.get(r, set()) - self.expected.get(r, set()))}
                 for r in sorted(set(got) | set(self.expected))
                 if got.get(r, set()) != self.expected.get(r, set())}
        self.assertEqual(diffs, {},
                         "grounding=%r differs from reachable.json: %s"
                         % (grounding, diffs))

    def test_rank_grounding_matches_the_oracle(self):
        self._assert_matches_oracle(GROUNDING_RANK)

    def test_flow_grounding_matches_the_oracle(self):
        self._assert_matches_oracle(GROUNDING_FLOW)

    def test_both_groundings_produce_the_identical_matrix(self):
        """ Stronger than each matching the oracle separately: had both been
        wrong in the same way the oracle comparison would catch it, but a
        per-pair disagreement between the two encodings is a soundness
        question about ad6 itself, and this is where it would surface. """
        self.assertEqual(self.matrices[GROUNDING_RANK],
                         self.matrices[GROUNDING_FLOW])

    def test_the_matrix_is_not_vacuous(self):
        """ Non-vacuity guard: an adapter that answered "unreachable" for
        everything would produce empty sets and match nothing, but an adapter
        that answered "reachable" for everything would still need this. """
        self.assertEqual(
            sum(len(v) for v in self.matrices[GROUNDING_FLOW].values()), 70,
            "wl_ifi's oracle is 70 reachable pairs: 54 between distinct roles "
            "plus one SELF-pair per role since commit 7ec21124 (TODO.md item "
            "14) -- each of the 16 roles abstracts a proper subnet, so its "
            "self-rule is a real compliance question and the switch answers it "
            "locally")


if __name__ == '__main__':
    unittest.main()
