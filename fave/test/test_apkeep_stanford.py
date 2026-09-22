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

""" APKeep on wl_stanford (Stanford backbone HSA) -- APKEEP_BACKEND.md, P7.

wl_stanford decomposes each of 16 routers into in./mid./out. switches. mid. is a
dst-IP FIB; in. is the ingress admission (in-port-qualified: it lists which
physical ports admit which VLANs); out. is an input-port->output-port permutation
(a pure wire) that a dst-IP ForwardElement cannot express. The adapter collapses
the out. stage into the topology, wiring each mid. egress interface straight to
its external neighbour (see APKeepAdapter._collapse_out_stage), so 48 switches
become 32 ForwardElements, and honours in-stage admission by dropping traffic
entering a port no rule admits (APKeepAdapter._gate_dead_ingress).

This pins forwarding correctness against the FAITHFUL data plane: FaVe+APKeep
reachability == FaVe+NetPlumber reachability (the two backends must agree exactly,
missing=0/extra=0). Both compute 165/240 router pairs: 5 source routers are
attached (by the shipped policy.json) to unconfigured interfaces that admit no
traffic -- e.g. roza gi4/8 (`no ip address`, member of no VLAN) -- so a real
router, NetPlumber, and (since the in-port admission fix) APKeep all drop them.

NOTE: this is deliberately NOT compared to reachable.json. That oracle is the
all-to-all *policy* (reach.txt: `All <--> All`, 240/240) from the original HSA/
NetPlumber papers -- an intended must-reach spec, not the data plane. The real
data plane violates it on exactly those 75 dead-port pairs; asserting APKeep==240
would require the in-port over-approximation the admission fix removes. The
separate-process APKeep-vs-NP differential is bench/apkeep_convergence.py.

NP must run in its OWN process (a resident JVM in-process makes NetPlumber
misreport), so its matrix is computed via the convergence harness's netplumber
worker subprocess. The model JSON are gitignored generated artifacts;
test/gen_wl_stanford_inputs.sh produces them from tracked inputs (no live backend).
"""

import logging
import os
import sys
import tempfile
import unittest

from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bench"))

_PREFIX = "bench/wl_stanford/stanford-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("device_topology.json", "routes.json", "sources.json", "probes.json")]


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_stanford inputs not generated (run test/gen_wl_stanford_inputs.sh)")
class TestAPKeepStanford(unittest.TestCase):
    """ Real wl_stanford -> APKeepAdapter (out-stage collapsed, in-stage admitted)
    -> reachability == FaVe+NetPlumber (the faithful data plane). """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_stanford")
        log.setLevel(logging.WARNING)
        # P7a measures the PLAIN out-stage collapse on the BDD engine; both are
        # explicit since the defaults became faithful/NDD (2026-09-18), and
        # faithful wl_stanford does not finish on BDD at all.
        cls.engine = APKeepAdapter(log, faithful_vlan=False, engine='bdd')

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
        # 16 routers x {in, mid, out}; the out. stage is collapsed into the
        # topology, so only the 16 in. + 16 mid. switches remain as DEVICES.
        self.assertTrue(self.engine._stanford)
        self.assertEqual(len(self.sources), 16)
        self.assertEqual(len(self.probes), 16)

        # ELEMENTS are more than devices, because ingress demultiplexing
        # (CLOUD_BENCH_PLAN.md §2.8) splits a device whose forwarding
        # discriminates among its ingress ports. Six in-stage routers do --
        # their rules send different ingress ports to different egress ports --
        # so 32 devices become 38 elements. The excess is a representational
        # cost of APKeep's per-device ForwardElement, not a change to the model,
        # and the reachability test below is what says the split is faithful.
        sep = self.engine.INGRESS_CLASS_SEP
        elements = self.engine._fwd_devices
        devices = {name.split(sep)[0] for name in elements}
        self.assertEqual(len(devices), 32)
        self.assertEqual(
            {d.split('.', 1)[0] for d in devices}, {'in', 'mid'},
            "the out. stage must still be collapsed out of the element set")
        split = sorted(d for d in devices
                       if sum(1 for e in elements if e.split(sep)[0] == d) > 1)
        self.assertEqual(len(split), 6, split)
        self.assertEqual(len(elements), 38)

    def test_reachability_matches_netplumber(self):
        # NetPlumber in a SEPARATE process (see module docstring); reuse the
        # convergence harness's netplumber worker to get its reachability matrix.
        import apkeep_convergence as conv
        with tempfile.TemporaryDirectory(prefix="stanford_np_") as tmp:
            np_matrix = conv._emit_worker("netplumber", None,
                                          os.path.join(tmp, "np.json"))
        np_reach = {role: set(srcs) for role, srcs in np_matrix.items()}
        diffs = {}
        for role in sorted(set(self.reach) | set(np_reach)):
            got = self.reach.get(role, set())
            exp = np_reach.get(role, set())
            if got != exp:
                diffs[role] = {"apkeep_only": sorted(got - exp),
                               "np_only": sorted(exp - got)}
        self.assertEqual(diffs, {},
                         "APKeep and NetPlumber disagree on the wl_stanford data "
                         "plane: %s" % diffs)


if __name__ == '__main__':
    unittest.main()
