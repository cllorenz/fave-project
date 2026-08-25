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

""" Full wl_stanford (all 16 routers) through Ad6Adapter, PLAIN (no VLAN
modelling) -- AD6_PLAN.md §5.4 Stage B, B1.

Mirrors `fave/test/test_apkeep_stanford.py` exactly (same benchmark, same
oracle, same discipline): drives the real 48-device wl_stanford model
(16 routers x in./mid./out.), collapses `out.*` into the topology
(Ad6Adapter._collapse_out_stage, B0), honours in-stage admission
(Ad6Adapter._capture_in_admit / favemodel.py's _gate_dead_ingress, B0),
and checks the result against a LIVE NetPlumber worker -- NOT
`reachable.json` (the all-to-all 240-pair POLICY, not the data plane; see
`[[stanford-forwarding-overapprox]]`) and NOT a recorded snapshot (the
live differential is what has caught every real bug in this project's
history, B0's own two bugs included). The oracle is NetPlumber==APKeep==165
(`test_apkeep_stanford.py`); this file is ad6's turn at the same bar.

CURRENT STATE (AD6_PLAN.md §5.4 Stage B, item 20 in ad6/FAVE_CHANGES.md):
item 19's cycle-soundness gap is now FIXED, correctly, via
Instantiator.SolveAcyclicEndToEnd (SCC-scoped rank/distance encoding,
lazily escalated only when a plain solve's witness turns out ungrounded
-- see that function's docstring and ad6/test/core/instantiatortest.py).
`test_out_stage_collapsed` passes. `test_reachability_matches_netplumber`
is SKIPPED BY DEFAULT (not failing, not passing) -- NOT because of a
correctness gap anymore, but because a real, instrumented full run (all
256 queries, AD6_BRIDGE_PROGRESS=1 live-logged) hit a 6-HOUR cap having
completed only 74/256 (28.9%) queries: 40 of those 74 needed the
escalation path, at 7.7s-2923s each (avg ~537s), consistent with the
backbone's redundant links pulling the vast majority of each router's own
per-table fallthrough chain into ONE giant strongly-connected component
(measured 86% of nodes on a 3-router slice alone) -- so the SCC-scoping
that helps in principle barely narrows anything on Stanford's actual
topology. PRIMARY finding (high confidence, directly observed): this
differential does not complete within 6 hours. SECONDARY finding (LOWER
confidence, a linear extrapolation of the observed rate, not an
independent measurement): a full run would likely take on the order of
20-21 hours. Per Claas: the 6-hour non-completion itself is the
reportable NO-GO result for the tool-comparison writeup -- deliberately
not re-run to actual completion. Opt in with
AD6_STANFORD_FULL_DIFFERENTIAL=1 (and a generous external timeout -- this
is a many-hour run, not a normal test) to exercise it anyway; set
AD6_BRIDGE_PROGRESS=1 and AD6_BRIDGE_PROGRESS_FILE=<path> (fave_bridge.py)
for live per-query progress, since Ad6Adapter.check_compliance captures
this script's stderr into a pipe that isn't readable until the whole
(possibly many-hour) subprocess exits. """

import logging
import os
import tempfile
import unittest

from ad6.adapter import Ad6Adapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_stanford/stanford-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("device_topology.json", "routes.json", "sources.json", "probes.json")]

# AD6_PLAN.md §5.4 Stage B, item 20: the full 256-query differential is a
# many-hour run (measured: 6+ hours, incomplete -- see the module
# docstring), not a normal test -- opt-in only, so a routine `test.sh`/CI
# run never silently hangs for hours. Deliberately a SEPARATE env var from
# FAVE_REQUIRE_BACKENDS/require_or_skip's "required" mode (backend_gate.py):
# that flag means "fail instead of skip if a BACKEND is unavailable", and
# must never be conflated with "run a many-hour differential to
# completion" -- CI setting FAVE_REQUIRE_BACKENDS=1 must not accidentally
# force this test to run for hours.
_RUN_FULL_DIFFERENTIAL = bool(os.environ.get("AD6_STANFORD_FULL_DIFFERENTIAL"))


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@require_or_skip(available(), "the ad6 fave_bridge.py script is unavailable")
@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_stanford inputs not generated (run test/gen_wl_stanford_inputs.sh)")
@unittest.skipUnless(
    _RUN_FULL_DIFFERENTIAL,
    "the full 256-query differential is a many-hour run that does not "
    "complete within 6 hours (AD6_PLAN.md §5.4 Stage B item 20, a "
    "reported NO-GO, not a bug) -- set AD6_STANFORD_FULL_DIFFERENTIAL=1 "
    "to opt in")
class TestAd6WlStanford(unittest.TestCase):
    """ Real wl_stanford (all 16 routers) -> Ad6Adapter (out-stage collapsed,
    in-stage admitted, B0) -> reachability == FaVe+NetPlumber (the faithful
    plain data plane). """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_ad6_wl_stanford")
        log.setLevel(logging.WARNING)
        cls.engine = Ad6Adapter(log)

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX, files=_FILES)
            cls.sources = sorted(cls.engine._generators)
            cls.probes = sorted(cls.engine._probes)
            rules = {p: [[s, False, []] for s in cls.sources] for p in cls.probes}
            fave.check_compliance(rules)

        not_reachable = {
            (s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()
        }
        cls.reach = {
            _base(p): set(
                _base(s) for s in cls.sources
                if (s, p) not in not_reachable and _base(s) != _base(p)
            )
            for p in cls.probes
        }

    def test_out_stage_collapsed(self):
        # 16 routers x {in, mid, out}; out.* is collapsed into the topology
        # (B0), so only the 16 in.* + 16 mid.* devices remain.
        ir = self.engine._build_ir()
        stages = {d.split('.', 1)[0] for d in ir["devices"]}
        self.assertEqual(stages, {'in', 'mid'})
        self.assertEqual(len(ir["devices"]), 32)
        self.assertEqual(len(self.sources), 16)
        self.assertEqual(len(self.probes), 16)

    def test_reachability_matches_netplumber(self):
        # NetPlumber in a SEPARATE process (a resident JVM/other backend
        # in-process makes it misreport) -- reuse the convergence harness's
        # netplumber worker, exactly like test_apkeep_stanford.py.
        from bench.apkeep_convergence import _emit_worker
        with tempfile.TemporaryDirectory(prefix="ad6_stanford_np_") as tmp:
            np_matrix = _emit_worker("netplumber", None, os.path.join(tmp, "np.json"))
        np_reach = {role: set(srcs) for role, srcs in np_matrix.items()}
        diffs = {}
        for role in sorted(set(self.reach) | set(np_reach)):
            got = self.reach.get(role, set())
            exp = np_reach.get(role, set())
            if got != exp:
                diffs[role] = {"ad6_only": sorted(got - exp),
                               "np_only": sorted(exp - got)}
        self.assertEqual(diffs, {},
                         "ad6 and NetPlumber disagree on the wl_stanford data "
                         "plane: %s" % diffs)


if __name__ == '__main__':
    unittest.main()
