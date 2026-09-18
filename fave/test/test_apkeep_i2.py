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

""" APKeep scale validation on the PLAIN wl_i2 (Internet2) model -- APKEEP_BACKEND.md, P5.

wl_i2 is the large workload: 9 routers decomposed into 18 in/out switches with a
~77k-entry destination-IP FIB. This drives the plain (`faithful_vlan=False`)
model on the BDD engine, which is a scale gate first and foremost.

WHAT IS AND IS NOT CLAIMED HERE. The plain model drops the VLAN dimension, so it
over-approximates BY CONSTRUCTION -- relaxing a constraint can only add
reachability. It reports all 72 pairs reachable where the real data plane
delivers 61. This file used to assert equality with `bench/wl_i2/reachable.json`
and describe that as "the adapter translates it exactly", which was wrong twice
over: `reachable.json` is the all-to-all POLICY mesh (72/72 reachable), so any
over-approximating encoding scores 100% on it by construction, and the model
being gated here is the one that over-approximates. The match was real; the
exactness reading was not.

So the oracle is `bench/wl_i2/eval/i2_structural_oracle_atoms.json` (exhaustive over
IPv4, agreed by NetPlumber and ad6), and what is asserted of the plain model is:

  * it reaches EVERY pair (the measured fact -- this is what the old assertion
    was really observing, since `reachable.json` is the all-72 mesh);
  * SOUNDNESS -- no pair the real data plane delivers may be dropped;
  * its over-approximation is exactly the 11 pairs the VLAN admission blocks.

BE PRECISE ABOUT THE STRENGTH: while the plain model reaches all 72, those three
are equivalent -- the last two follow algebraically from the first, so they add
no detection power over the old `reachable.json` comparison. Verified, not
assumed: dropping a pair from the oracle leaves the two-sided form passing. What
changes is ATTRIBUTION. Each assertion now names the property it stands for and
is checked against the real data plane rather than against policy intent, so if
the plain model is ever tightened the failure says whether it lost something
deliverable (unsound) or shed one of the 11 (a real improvement). The old form
could only say "differs from reachable.json" and read as a claim that the model
is exact, which it is not.

Exactness is gated where it belongs: on the FAITHFUL model, in
`test_apkeep_ndd_fwd.py:test_i2_faithful_vlan_matches_the_structural_oracle`,
where equality with the oracle is a real, falsifiable assertion.

This is the correctness companion to the from-zero scale comparison in
bench/apkeep_vs_netplumber.py (where APKeep is ~24x faster than NetPlumber here).
The model JSON are gitignored generated artifacts; test/gen_wl_i2_inputs.sh
produces them from tracked inputs before this runs (no live backend). Heavier
than the wl_ifi test (~15 s) -- a deterministic scale gate, not a fast check.
"""

import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip
from test.i2_oracle import load_unreachable, plain_model_violations

_PREFIX = "bench/wl_i2/i2-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
# The structural oracle (tracked): the 11 (source, probe) pairs the real wl_i2
# data plane does NOT deliver, exhaustive over IPv4 and agreed by NetPlumber and
# ad6. NOT `reachable.json`, which is the all-to-all policy intent.
_ORACLE = "bench/wl_i2/eval/i2_structural_oracle_atoms.json"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("device_topology.json", "routes.json", "sources.json", "probes.json")] + [_ORACLE]


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_i2 inputs not generated (run test/gen_wl_i2_inputs.sh)")
class TestAPKeepI2(unittest.TestCase):
    """ Real wl_i2 (77k dst-IP routes) -> APKeepAdapter, plain model: complete,
    and over-approximate by exactly the documented amount. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_i2")
        log.setLevel(logging.WARNING)
        # The plain dst-only i2 model on the BDD engine, explicitly: the faithful
        # one is now the default and does not finish on BDD (§2.6b).
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
        # (source, probe) base-name pairs, self-pairs excluded -- the shape the
        # structural oracle records.
        cls.got = {
            (_base(s), _base(p))
            for p in cls.probes for s in cls.sources
            if (s, p) not in not_reachable and _base(s) != _base(p)
        }
        cls.all_pairs = {
            (_base(s), _base(p))
            for p in cls.probes for s in cls.sources if _base(s) != _base(p)
        }
        cls.unreachable = load_unreachable(_ORACLE)
        cls.truly_reachable = cls.all_pairs - cls.unreachable

    def test_scale_model_built(self):
        # 9 routers -> 18 in/out switches; a large dst-IP FIB.
        self.assertEqual(len(self.engine._fwd_devices), 18)
        self.assertEqual(len(self.sources), 9)
        self.assertEqual(len(self.probes), 9)
        self.assertGreater(len(self.engine._fwd_rules), 50000)

    def test_the_plain_model_behaves_as_documented(self):
        """ Reaches every pair, drops nothing the data plane delivers, and
        over-approximates by exactly the 11 VLAN-blocked pairs -- judged by
        `test/i2_oracle.py`, shared with the NDD gate so the two engines are held
        to the same statement. See that module on what the three do and do not
        detect. """
        self.assertEqual(
            plain_model_violations(self.got, self.all_pairs, self.unreachable), [])


if __name__ == '__main__':
    unittest.main()
