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

""" Full wl_up end-to-end through the APKeepAdapter driving the NDD engine
(APKEEP_NDD_PLAN.md §2.5e productionization).

This is the productionized counterpart of the §2.5c/d Java prototype
(NDDWlupReachabilityTest): instead of line-file dumps, it drives the *real*
wl_up device models through the *real* aggregator dispatch (InProcessFaVe wraps
an in-process AggregatorService whose engine is APKeepAdapter(engine='ndd')),
computes the full source->probe reachability matrix, and asserts EXACT parity
with the frozen BDD baseline matrix (bench/wl_up/eval/mat_apk.json, the golden
the BDD engine produced -- 3661 raw pairs). Proves "one shared adapter, two
engines": the same model construction, dispatched to the per-field NDD engine,
reproduces the BDD result bit-for-bit.
"""

import json
import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_ndd import available as ndd_available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_up"
_GOLDEN = "%s/eval/mat_apk.json" % _PREFIX

# wl_up model JSON (tracked) + the frozen BDD golden matrix.
_INPUTS = [
    "%s/%s" % (_PREFIX, f) for f in
    ("topology.json", "routes.json", "sources.json", "policies.json")
] + [_GOLDEN]


def _inputs_present():
    return all(os.path.isfile(f) for f in _INPUTS)


@require_or_skip(ndd_available(), "JPype or the NDD jar is unavailable")
@require_or_skip(_inputs_present(), "wl_up inputs not present")
class TestAPKeepNddWlup(unittest.TestCase):
    """ Real wl_up -> APKeepAdapter(engine='ndd') -> reachability, which must
    match the frozen BDD baseline matrix exactly (0 over, 0 under). """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_ndd_wlup")
        log.setLevel(logging.WARNING)
        cls.engine = APKeepAdapter(log, engine='ndd')

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            cls.sources = sorted(cls.engine._generators)  # "source.X"
            cls.probes = sorted(cls.engine._probes)        # "probe.Y"
            # "must reach" for every (source, probe); a recorded violation means
            # the pair is NOT reachable.
            rules = {p: [[s, False, []] for s in cls.sources] for p in cls.probes}
            fave.check_compliance(rules)

        not_reachable = {
            (s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()
        }
        # Full reachability matrix as "probe source" pairs (raw, self-pairs
        # included -- exactly the shape of the frozen golden).
        cls.got = {
            "%s %s" % (p, s)
            for p in cls.probes for s in cls.sources
            if (s, p) not in not_reachable
        }
        gmat = json.load(open(_GOLDEN))
        cls.golden = {
            "%s %s" % (p, s) for p, slist in gmat.items() for s in slist
        }

    def test_network_built(self):
        # wl_up: 137 sources + 137 probes, single-universe forwarding.
        self.assertEqual(len(self.sources), 137)
        self.assertEqual(len(self.probes), 137)
        self.assertTrue(self.engine.single_universe())

    def test_reachability_exact_parity_with_bdd_baseline(self):
        """ NDD engine == frozen BDD baseline, pair-for-pair (0 over, 0 under). """
        over = self.got - self.golden    # NDD reachable, BDD not
        under = self.golden - self.got   # BDD reachable, NDD not (unsound)
        self.assertEqual(
            len(under), 0,
            "UNSOUND: BDD-reachable pairs the NDD engine drops: %s"
            % sorted(under)[:20])
        self.assertEqual(
            len(over), 0,
            "OVER: pairs the NDD engine adds vs the BDD baseline: %s"
            % sorted(over)[:20])
        self.assertEqual(len(self.got), len(self.golden))


if __name__ == '__main__':
    unittest.main()
