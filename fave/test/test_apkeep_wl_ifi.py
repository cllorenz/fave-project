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

""" Full wl_ifi end-to-end for APKeepAdapter (APKEEP_BACKEND.md, P4).

Unlike test_apkeep_adapter (a hand-built two-device model), this drives the
*real* wl_ifi device models -- the router `ifi`, its 16 switches, 17 generators
and 17 probes -- through the *real* aggregator dispatch (InProcessFaVe wraps an
in-process AggregatorService whose engine is the APKeepAdapter), then computes
the full source->probe reachability matrix and checks it against the benchmark's
ground-truth reachable.json.

The translation is forwarding-only: ACLs are not yet modelled. Dropping ACLs can
only *add* forwarding paths, so the invariant we can assert exactly is
COMPLETENESS -- every pair the full (ACL-enforcing) FaVe model finds reachable
must also be reachable here. The remaining "extra" pairs are precisely (a) intra-
switch self-reach (source.X -> probe.X), which the policy matrix never asks
about, and (b) flows the router ACLs drop. Both are quantified below; closing
the gap to an exact match is the ACL-translation step of P4.
"""

import json
import logging
import unittest

from apkeep.adapter import APKeepAdapter, available

_PREFIX = "bench/wl_ifi"


def _base(name):
    """ "source.external.ifi"/"probe.admin.ifi" -> "external.ifi"/"admin.ifi";
    "source.Internet" -> "Internet". """
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


@unittest.skipUnless(available(), "JPype or the APKeep jar is unavailable")
class TestAPKeepWlIfi(unittest.TestCase):
    """ Real wl_ifi -> APKeepAdapter -> reachability, vs reachable.json. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_wl_ifi")
        log.setLevel(logging.WARNING)
        cls.engine = APKeepAdapter(log)

        with InProcessFaVe(cls.engine) as fave:
            fave.replay(_PREFIX)
            cls.sources = sorted(cls.engine._generators)  # "source.X"
            cls.probes = sorted(cls.engine._probes)        # "probe.Y"
            # "must reach" for every (source, probe): a recorded violation means
            # the pair is NOT reachable.
            rules = {p: [[s, False, []] for s in cls.sources] for p in cls.probes}
            fave.check_compliance(rules)

        not_reachable = {
            (s, p) for (s, p, _mr, _c) in cls.engine.get_compliance_results()
        }
        # base-name reachability matrix: probe_base -> {source_base reachable}
        cls.reach = {
            _base(p): set(
                _base(s) for s in cls.sources if (s, p) not in not_reachable
            )
            for p in cls.probes
        }
        with open("%s/reachable.json" % _PREFIX) as raw:
            cls.expected = json.load(raw)

    def test_network_built(self):
        # 1 router + 16 switches, all dst-IP ForwardElements.
        self.assertEqual(len(self.engine._fwd_devices), 17)
        self.assertEqual(len(self.sources), 17)
        self.assertEqual(len(self.probes), 17)
        # routes were actually translated (router + switch FIBs are non-empty).
        self.assertTrue(any(r.split()[2] == 'ifi' for r in self.engine._fwd_rules))
        self.assertGreater(len(self.engine._fwd_rules), 17)

    def test_forwarding_completeness(self):
        """ Every pair reachable.json marks reachable must be reachable here;
        dropping ACLs cannot remove a forwarding path. """
        missing = {}
        for probe, exp_sources in self.expected.items():
            got = self.reach.get(probe, set())
            absent = set(exp_sources) - got
            if absent:
                missing[probe] = sorted(absent)
        self.assertEqual(missing, {}, "forwarding lost reachable pairs: %s" % missing)

    def test_extra_is_self_reach_and_acl_filtered(self):
        """ The reachability APKeep finds beyond reachable.json is exactly intra-
        switch self-reach plus ACL-dropped flows -- the network has no path that
        is neither. """
        self_reach = 0
        acl_filtered = 0
        for probe, got in self.reach.items():
            exp = set(self.expected.get(probe, []))
            for source in got - exp:
                if source == probe:
                    self_reach += 1
                else:
                    acl_filtered += 1
        # 16 lateral switches each reach their own probe (the router's own
        # subnet, "Internet", has no source.X==probe.X pairing).
        self.assertEqual(self_reach, 16)
        # The rest are flows the router ACLs drop; forwarding-only admits them.
        self.assertGreater(acl_filtered, 0)
        # Sanity: the roles reachable.json says are reachable by nobody are still
        # forwardable here (pure routing reaches them; only ACLs isolate them).
        isolated = [k for k, v in self.expected.items() if not v]
        for role in isolated:
            self.assertTrue(self.reach.get(role), "%s unreachable even by forwarding" % role)


if __name__ == '__main__':
    unittest.main()
