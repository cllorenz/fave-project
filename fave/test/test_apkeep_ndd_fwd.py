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

""" IPv4 forwarding benchmarks on the NDD engine (APKEEP_NDD_PLAN §2.6, incr 1):
wl_i2 (77k dst-IP ForwardElement routes), wl_stanford P7a (in/mid collapsed
forwarding) and wl_tum (IPv4 5-tuple FilterElement). Each is driven through the
same adapter with engine='ndd' and gated at EXACT parity:

  * wl_i2       -> the tracked ground truth reachable.json (role matrix), the
                  same oracle the BDD test asserts (so NDD == BDD == oracle).
  * wl_stanford -> a differential against engine='bdd' in the same process
  * wl_tum      -> a differential against engine='bdd' in the same process

The stanford/tum oracles are live NetPlumber in the BDD tests; here we use the
already-gated BDD engine as the baseline (differential vs BDD is the plan's
primary NDD correctness lever), which keeps these tests self-contained.
"""

import json
import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_ndd import available as ndd_available
from test.backend_gate import require_or_skip


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _matrix(prefix, engine, files=None, faithful=False):
    """ Full source->probe reachability as a set of (source, probe) reachable
    pairs, driving the real aggregator into APKeepAdapter(engine=...). """
    from util.in_process_driver import InProcessFaVe
    log = logging.getLogger("ndd_fwd"); log.setLevel(logging.WARNING)
    eng = APKeepAdapter(log, faithful_vlan=faithful, engine=engine)
    with InProcessFaVe(eng) as fave:
        if files:
            fave.replay(prefix, files=files)
        else:
            fave.replay(prefix)
        sources = sorted(eng._generators)
        probes = sorted(eng._probes)
        rules = {p: [[s, False, []] for s in sources] for p in probes}
        fave.check_compliance(rules)
    not_reach = {(s, p) for (s, p, _mr, _c) in eng.get_compliance_results()}
    reach = {(s, p) for p in probes for s in sources if (s, p) not in not_reach}
    return eng, sources, probes, reach


_I2_PREFIX = "bench/wl_i2/i2-json"
_I2_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_I2_ORACLE = "bench/wl_i2/reachable.json"
_I2_INPUTS = ["%s/%s" % (_I2_PREFIX, f) for f in
              ("device_topology.json", "routes.json", "sources.json",
               "probes.json")] + [_I2_ORACLE]

_IFI_PREFIX = "bench/wl_ifi"
_IFI_ORACLE = "bench/wl_ifi/reachable.json"
_IFI_INPUTS = ["%s/%s" % (_IFI_PREFIX, f) for f in
               ("topology.json", "routes.json", "sources.json", "policies.json")] + [_IFI_ORACLE]

_ST_PREFIX = "bench/wl_stanford/stanford-json"
_ST_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_ST_INPUTS = ["%s/%s" % (_ST_PREFIX, f) for f in
              ("device_topology.json", "routes.json", "sources.json", "probes.json")]

_TUM_PREFIX = "bench/wl_tum"
_TUM_INPUTS = ["%s/%s" % (_TUM_PREFIX, f) for f in
               ("topology.json", "routes.json", "policies.json", "sources.json",
                "rulesets/tum-ruleset")]


@require_or_skip(ndd_available(), "JPype or the NDD jar is unavailable")
class TestNddIPv4Forwarding(unittest.TestCase):
    """ IPv4 forwarding (+fwd) and IPv4 5-tuple (+filter) on the NDD engine. """

    @require_or_skip(all(os.path.isfile(f) for f in _I2_INPUTS),
                     "wl_i2 inputs not generated (run test/gen_wl_i2_inputs.sh)")
    def test_i2_matches_ground_truth(self):
        """ wl_i2 (77k dst-IP routes) NDD reachability == reachable.json. Routed
        to the atomic-predicate forwarding engine (AtomForwarding): elementary
        dst intervals + per-device LPM + signature-merge to the minimal 216-atom
        partition (= APKeep's ap_num), atom-set flood -- builds in ~0.7s where the
        monolithic residual OOMs/times out. See APKEEP_NDD_EVAL.md §2.6. """
        eng, sources, probes, reach = _matrix(_I2_PREFIX, 'ndd', files=_I2_FILES)
        got = {
            _base(p): set(_base(s) for s in sources
                          if (s, p) in reach and _base(s) != _base(p))
            for p in probes
        }
        with open(_I2_ORACLE) as raw:
            expected = json.load(raw)
        diffs = {}
        for role in sorted(set(got) | set(expected)):
            g = got.get(role, set())
            e = set(expected.get(role, []))
            if g != e:
                diffs[role] = {"missing": sorted(e - g), "extra": sorted(g - e)}
        self.assertEqual(diffs, {}, "wl_i2 NDD differs from reachable.json: %s" % diffs)

    @require_or_skip(all(os.path.isfile(f) for f in _IFI_INPUTS),
                     "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
    def test_ifi_matches_ground_truth(self):
        """ wl_ifi (forwarding + router ACLs) NDD reachability == reachable.json
        (the same oracle the BDD test asserts). The source's src-IP seeds the
        query so source-matching ACLs bite; a probe.X<-source.X self-reach never
        hits the router (not ACL-filtered), so it is excluded as reachable.json
        omits it. """
        eng, sources, probes, reach = _matrix(_IFI_PREFIX, 'ndd')
        got = {
            _base(p): set(_base(s) for s in sources
                          if (s, p) in reach and _base(s) != _base(p))
            for p in probes
        }
        with open(_IFI_ORACLE) as raw:
            expected = json.load(raw)
        diffs = {}
        for role in sorted(set(got) | set(expected)):
            g = got.get(role, set())
            e = set(expected.get(role, []))
            if g != e:
                diffs[role] = {"missing": sorted(e - g), "extra": sorted(g - e)}
        self.assertEqual(diffs, {}, "wl_ifi NDD differs from reachable.json: %s" % diffs)

    @require_or_skip(all(os.path.isfile(f) for f in _ST_INPUTS),
                     "wl_stanford inputs not generated (run test/gen_wl_stanford_inputs.sh)")
    def test_stanford_p7a_matches_bdd(self):
        """ wl_stanford P7a forwarding: NDD == BDD, pair-for-pair. """
        _, _, _, bdd = _matrix(_ST_PREFIX, 'bdd', files=_ST_FILES)
        _, _, _, ndd = _matrix(_ST_PREFIX, 'ndd', files=_ST_FILES)
        self.assertEqual(bdd - ndd, set(), "UNSOUND: BDD-reachable pairs NDD drops")
        self.assertEqual(ndd - bdd, set(), "OVER: pairs NDD adds vs BDD")

    @require_or_skip(all(os.path.isfile(f) for f in _TUM_INPUTS),
                     "wl_tum inputs missing")
    def test_tum_matches_bdd(self):
        """ wl_tum IPv4 5-tuple firewall: NDD == BDD, pair-for-pair. """
        _, _, _, bdd = _matrix(_TUM_PREFIX, 'bdd')
        _, _, _, ndd = _matrix(_TUM_PREFIX, 'ndd')
        self.assertEqual(bdd - ndd, set(), "UNSOUND: BDD-reachable pairs NDD drops")
        self.assertEqual(ndd - bdd, set(), "OVER: pairs NDD adds vs BDD")

    @require_or_skip(all(os.path.isfile(f) for f in _ST_INPUTS),
                     "wl_stanford inputs not generated")
    def test_stanford_faithful_vlan_matches_netplumber(self):
        """ Faithful wl_stanford VLAN model on NDD (per-router VLAN admission +
        per-route VLAN rewrite + access-port untag at probes) == the NetPlumber
        data plane, pair-for-pair. This is the case BDD-APKeep cannot finish (the
        VLAN x dst atomic-predicate cross-product explodes to ~21k APs, 28 min+
        unfinished); NDD builds it in ~3 s. NP is the oracle (we've shown NP ==
        BDD-APKeep on the tractable configs); see APKEEP_NDD_EVAL.md §2.6. """
        import sys
        sys.path.insert(0, os.path.abspath("bench"))
        from netplumber import lib_adapter
        if lib_adapter.libnetplumber is None:
            self.skipTest("libnetplumber not built")
        import apkeep_convergence as conv
        np = conv.compute_matrix("netplumber", None)   # probe base -> src bases
        np_pairs = {(p, s) for p, ss in np.items() for s in ss}

        _, sources, probes, reach = _matrix(
            _ST_PREFIX, 'ndd', files=_ST_FILES, faithful=True)
        ndd_pairs = {
            (_base(p), _base(s)) for p in probes for s in sources
            if (s, p) in reach and _base(s) != _base(p)
        }
        self.assertEqual(np_pairs - ndd_pairs, set(),
                         "UNSOUND: NP-reachable faithful pairs NDD drops")
        self.assertEqual(ndd_pairs - np_pairs, set(),
                         "OVER: faithful pairs NDD adds vs NP")


if __name__ == '__main__':
    unittest.main()
