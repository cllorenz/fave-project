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

""" wl_stanford through Ad6Adapter, PLAIN (no VLAN modelling at all) --
AD6_PLAN.md §5.4 Stage B, B0.

No wl_stanford<->ad6 translator existed before this. Unlike wl_ifi/wl_up
(Cisco-ACL router / ip6tables ruleset shapes), wl_stanford's devices are
`SwitchModel`s named `in.<router>`/`mid.<router>`/`out.<router>` (48 = 16
routers x 3 stages), each with exactly one table `"<device>.1"`. B0 proves
out the PLAIN target only (LPM forwarding + a binary per-physical-port
dead-ingress gate -- no VLAN admission, no VLAN rewrite): the oracle this
must match is NetPlumber==APKeep==165 reachable pairs on the full 16-router
model (`[[stanford-forwarding-overapprox]]`); this file's differential test
checks a small induced 2-router slice (`bbra_rtr,rozb_rtr` -- the same one
`fave/bench/apkeep_convergence.py`'s own faithful-VLAN measurement uses)
against a LIVE NetPlumber worker, not a recorded snapshot -- the full
16-router differential is §5.4 Stage B1, not this file.

Two layers:
  - Unit tests (fake Rule/RuleField/Forward/Rewrite objects, no ad6
    binary/subprocess/benchmark inputs) for the two new Ad6Adapter
    mechanisms this benchmark's real data actually needs:
    the multi-port (ECMP) forwarding and blackhole/discard handling the
    translator has to get right at this scale.
  - A structural + differential test on the real N=2 slice, reusing
    `fave/bench/apkeep_convergence.py`'s own model-filtering/worker
    machinery for a true apples-to-apples comparison.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest

from ad6.adapter import Ad6Adapter, available
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField
from test.backend_gate import require_or_skip

_DST = 'packet.ipv4.destination'
_VLAN = 'packet.ether.vlan'

_STANFORD_DIR = os.path.join("bench", "wl_stanford", "stanford-json")
_STANFORD_FILES = ("device_topology.json", "routes.json", "probes.json", "sources.json")


def _inputs_present():
    return all(os.path.isfile(os.path.join(_STANFORD_DIR, f)) for f in _STANFORD_FILES)


def _fwd_rule(idx, dst=None, ports=(), in_ports=()):
    match = Match([RuleField(_DST, dst)]) if dst is not None else Match([])
    actions = [Forward(ports=list(ports))] if ports else []
    return Rule('dev', 'mid.dev.1', idx, in_ports=list(in_ports), match=match, actions=actions)


class TestAd6WlStanfordPlainN2(unittest.TestCase):
    """ Structural + differential check on the real N=2 induced slice
    (`bbra_rtr,rozb_rtr` -- the same subset
    `fave/bench/apkeep_convergence.py`'s own faithful-VLAN measurement
    uses), against a LIVE NetPlumber worker (not a recorded snapshot --
    same discipline as `fave/test/test_apkeep_stanford.py`, and as §5.4
    Stage B1's own full-scale plan). CAVEAT (from
    `apkeep_convergence.py`'s own module docstring): an induced subnetwork
    poses a NEW, self-contained forwarding problem -- it does not have to
    reproduce the full 16-router model's per-pair verdict, only agree
    with NetPlumber on ITS OWN (smaller) verdict. """

    _ROUTERS = {"bbra_rtr", "rozb_rtr"}

    @classmethod
    def setUpClass(cls):
        from bench.apkeep_convergence import (
            _FILES, _base, _filter_model, _load_model, _write_model, _emit_worker,
        )
        from util.in_process_driver import InProcessFaVe

        model = _filter_model(_load_model(), cls._ROUTERS)
        cls._tmp = tempfile.TemporaryDirectory(prefix="ad6_stanford_n2_")
        _write_model(model, cls._tmp.name)

        log = logging.getLogger("test_ad6_wl_stanford_plain_n2")
        log.setLevel(logging.WARNING)
        cls.engine = Ad6Adapter(log)
        with InProcessFaVe(cls.engine) as fave:
            fave.replay(cls._tmp.name, files=_FILES)
            sources = sorted(cls.engine._generators)
            probes = sorted(cls.engine._probes)
            rules = {p: [[s, False, []] for s in sources] for p in probes}
            fave.check_compliance(rules)

        not_reached = {(s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()}
        cls.ad6_matrix = {
            _base(p): sorted(
                _base(s) for s in sources
                if (s, p) not in not_reached and _base(s) != _base(p)
            )
            for p in probes
        }

        with tempfile.TemporaryDirectory(prefix="ad6_stanford_n2_np_") as np_tmp:
            cls.np_matrix = _emit_worker(
                "netplumber", cls._ROUTERS, os.path.join(np_tmp, "np.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_every_stage_is_kept_including_out(self):
        """ AD6_PLAN.md §9.25 INVERTS this test, deliberately.

        It used to assert that `out.*` was entirely COLLAPSED away -- 2 routers
        x (in, mid) = 4 devices -- because the semantic path recognised a
        wl_stanford out-stage as a pure port permutation and dropped it. That
        collapse was name-triggered (`if any(d.split('.', 1)[0] == 'mid' ...)`),
        which is exactly what §9 exists to remove, so it went with the rest of
        that path.

        A structural translation keeps every stage FaVe declares. The
        reachability test below is unchanged and still matches NetPlumber
        exactly, which is what says the collapse was an optimisation and not a
        correctness requirement. Phase 3 flagged the size cost this implies; if
        the collapse ever returns it must be a STRUCTURAL rule ("collapse any
        table that is a pure port permutation"), stamped and toggleable, never
        keyed on a device name. """
        stages = {d.split('.', 1)[0] for d in self.engine._tables}
        self.assertEqual(stages, {'in', 'mid', 'out'})
        self.assertEqual(len(self.engine._tables), 6)  # 2 routers x 3 stages

    def test_reachability_matches_netplumber_on_the_induced_slice(self):
        def pairs(matrix):
            return {(s, p) for p, srcs in matrix.items() for s in srcs}

        ad6_pairs, np_pairs = pairs(self.ad6_matrix), pairs(self.np_matrix)
        under = np_pairs - ad6_pairs   # NetPlumber reachable, ad6 drops it: unsound
        over = ad6_pairs - np_pairs    # ad6 reachable, NetPlumber doesn't: over-approx
        self.assertEqual(
            under, set(),
            "ad6 UNSOUND on the N=2 slice -- dropped a pair NetPlumber reaches: %s" % under)
        self.assertEqual(
            over, set(),
            "ad6 over-approximates on the N=2 slice vs NetPlumber: %s" % over)


if __name__ == '__main__':
    unittest.main()
