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

""" wl_stanford's faithful VLAN admission gate is keyed by (ingress port, VLAN)
and sits on the arrival edge -- APKEEP_BACKEND.md Sec. 9.

`_build_stanford_faithful` used to splice ONE ACLElement per router onto that
router's single `in.X -> mid.X` internal edge, permitting the union of every
ingress port's admitted VLANs. wl_i2's builder had the same port-blind keying
and it cost 11 reachability pairs there; wl_stanford was never observed to be
wrong, because the surplus tags happen to be ones nothing upstream assigns
towards those ports. The over-approximation is real all the same -- the union
strictly exceeds the per-port set at all 16 routers -- and it could not be fixed
where it stood: the `in.X -> mid.X` funnel is downstream of the merge, so the
arrival port is already lost there.

This pins the structure rather than a reachability verdict, for two reasons.
The verdict is already gated (`test_apkeep_ndd_fwd.py`'s faithful wl_stanford
test asserts pair-for-pair equality with NetPlumber), and it CANNOT see this
defect -- it passed both before and after the fix. A structural assertion is
what distinguishes "right answer" from "right answer for the right reason".

Consumes the same generated wl_stanford model the other wl_stanford tests do
(`test/gen_wl_stanford_inputs.sh`; gitignored artifacts), and skips without it.
Builds no engine: the splice is pure Python over the captured model.
"""

import logging
import os
import unittest

from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

_PREFIX = "bench/wl_stanford/stanford-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("device_topology.json", "routes.json", "sources.json", "probes.json")]


def _vlans(acl_rule):
    """ The VLAN tag set of an "+ acl ..." rule string (the trailing token; see
    `_acl_rule_string`). """
    return set(acl_rule.split()[-1].split(','))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_stanford inputs not generated (run test/gen_wl_stanford_inputs.sh)")
class TestStanfordAdmissionIsPerPort(unittest.TestCase):
    """ One admission element per reached (in-stage device, ingress port), each
    permitting exactly that port's own VLAN set. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe

        log = logging.getLogger("test_apkeep_stanford_admission")
        log.setLevel(logging.WARNING)
        cls.adapter = APKeepAdapter(log, faithful_vlan=True, engine='ndd')
        with InProcessFaVe(cls.adapter) as fave:
            fave.replay(_PREFIX, files=_FILES)
        # `_build_stanford_faithful` is normally reached through `_build()`,
        # which would also stand up the whole NDD model; drive it directly.
        cls.adapter._stanford = True
        (cls.spliced, _nats, _nat_rules,
         cls.acls, cls.acl_rules) = cls.adapter._build_stanford_faithful(
             list(cls.adapter._edges))

    def _admitted(self, device, port):
        anyport = {d: v for (d, p), v in self.adapter._in_port_vlans.items()
                   if p is None}
        return (self.adapter._in_port_vlans.get((device, port), set())
                | anyport.get(device, set()))

    def test_the_model_really_is_port_non_uniform(self):
        """ Without this the rest of the file could pass on a model where the
        union and the per-port sets coincide, proving nothing. """
        by_device = {}
        for (device, port), vlans in self.adapter._in_port_vlans.items():
            if port is not None:
                by_device.setdefault(device, []).append(vlans)
        self.assertTrue(by_device, "no per-port admission was captured at all")
        for device, sets in sorted(by_device.items()):
            union = self.adapter._in_vlans[device]
            widest = max(len(s) for s in sets)
            self.assertLess(
                widest, len(union),
                "%s: the per-device union (%d tags) does not exceed its widest "
                "port (%d), so this model cannot discriminate the two keyings"
                % (device, len(union), widest))

    def test_one_admission_element_per_reached_ingress_port(self):
        reached = {
            (d_dev, d_port)
            for d_dev, d_port in (tuple(e.split()[2:4]) for e in self.adapter._edges)
            if self._admitted(d_dev, d_port)
        }
        self.assertEqual(len(self.acl_rules), len(reached))
        self.assertEqual(len(self.acls.get("iacl", [])), len(reached))
        # ... and more than one per router, or the keying is still per-device.
        routers = {dev for dev, _port in reached}
        self.assertGreater(len(reached), len(routers))

    def test_each_element_permits_exactly_its_own_ports_vlans(self):
        """ The defect in one assertion: a rule carrying the device union
        instead of the arrival port's set. """
        keys = sorted({
            (d_dev, d_port)
            for d_dev, d_port in (tuple(e.split()[2:4]) for e in self.adapter._edges)
            if self._admitted(d_dev, d_port)
        })
        for idx, (device, port) in enumerate(keys):
            rule = next(r for r in self.acl_rules
                        if r.split()[2] == "iacl_%d" % idx)
            with self.subTest(device=device, port=port):
                self.assertEqual(_vlans(rule), self._admitted(device, port))
                self.assertNotEqual(
                    _vlans(rule), self.adapter._in_vlans[device],
                    "%s port %s admits the whole device union -- port-blind"
                    % (device, port))

    def test_every_live_ingress_edge_passes_a_gate(self):
        """ Transit and source edges alike. The only edges left ungated deliver
        to ports NO rule admits, which `_gate_dead_ingress` removes outright. """
        ungated = [e for e in self.spliced
                   if e.split()[2].split('.', 1)[0] == 'in'
                   and not e.split()[0].startswith('iacl')]
        for edge in ungated:
            _s_dev, _s_port, d_dev, d_port = edge.split()
            admit = self.adapter._in_admit.get(d_dev)
            with self.subTest(edge=edge):
                self.assertIsNotNone(
                    admit, "%s admits every port, so this edge must be gated" % d_dev)
                self.assertNotIn(
                    d_port, admit,
                    "ungated ingress edge to a LIVE port: %s" % edge)


if __name__ == '__main__':
    unittest.main()
