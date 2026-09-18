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

""" wl_i2 faithful VLAN admission is per (ingress port, VLAN) and applies at
EVERY hop -- APKEEP_BACKEND.md Sec. 9, "the wl_i2 11-pair over-approximation".

The real wl_i2 in-stage admits a DIFFERENT VLAN set on each physical ingress
port (in.kans port 400029 admits {11,20,21,30,31,32,40,60,70} while ports
400007/400019/400022/400025/400026 admit 10), and a transit packet is checked
against the set of the port it actually arrives on. Both properties are load-
bearing: `bench/i2_structural_oracle.py` re-run with either one relaxed reports
72 of 72 reachable pairs instead of the true 61, which is exactly the answer
APKeep gave.

This pins them on a two-router model shaped like wl_i2's in/out decomposition:

    source.S -> in.b:1 --> out.b (dst 10/8 -> port 2, rw vlan:10)
             -> in.a:5 --> out.a (dst 10/8 -> port 9, rw vlan:0) -> probe.P

`in.a` admits VLAN 99 on port 5 (where the transit link lands) and VLAN 10 on
port 6 (where nothing lands). So the VLAN 10 that `out.b` writes is NOT admitted
and probe.P is unreachable. A port-blind union ({10,99}) admits it; so does
gating only the source's ingress edge and letting transit through ungated.
Either mistake turns this into a false "reachable".
"""

import unittest

from types import SimpleNamespace

from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

_DST = 'packet.ipv4.destination'
_VLAN = 'packet.ether.vlan'


def _logger():
    import logging
    log = logging.getLogger("test_apkeep_i2_admission")
    log.setLevel(logging.WARNING)
    return log


def _in_stage(node, admissions):
    """ An in.X stage: per (ingress port, VLAN) admission, forwarding to the
    single internal port that funnels on to out.X. """
    table = node + '.1'
    return SimpleNamespace(node=node, tables={table: [
        Rule(node, table, idx, ['%s.%s' % (node, port)],
             Match([RuleField(_VLAN, str(vlan))]),
             [Forward(['%s.100' % node])])
        for idx, (port, vlan) in enumerate(admissions)
    ]})


def _out_stage(node, dst, egress, vlan):
    """ An out.X stage: the real dst-IP FIB, which also rewrites the egress
    VLAN (wl_i2's `rw=vlan:M`). """
    table = node + '.1'
    return SimpleNamespace(node=node, tables={table: [
        Rule(node, table, 0, ['%s.110' % node],
             Match([RuleField(_DST, dst)]),
             [Rewrite([RuleField(_VLAN, str(vlan))]),
              Forward(['%s.%s' % (node, egress)])])
    ]})


def _build(engine):
    adapter = APKeepAdapter(_logger(), faithful_vlan=True, engine=engine)
    models = [
        _in_stage('in.b', [('1', 0)]),              # source lands on port 1, VLAN 0
        _out_stage('out.b', '10.0.0.0/8', '2', 10),  # transit egress writes VLAN 10
        # port 5 carries the transit link and admits 99 only; 10 is admitted on
        # port 6, where nothing arrives -- the union would wrongly admit it.
        _in_stage('in.a', [('5', 99), ('6', 10)]),
        _out_stage('out.a', '10.0.0.0/8', '9', 0),   # untagged towards the probe
    ]
    for model in models:
        adapter.add_tables(model)
        adapter.add_rules(model)
    for sport, dport in [("source.S.1", "in.b.1"), ("in.b.100", "out.b.110"),
                         ("out.b.2", "in.a.5"), ("in.a.100", "out.a.110"),
                         ("out.a.9", "probe.P.1")]:
        adapter.add_link(sport, dport)
    adapter.add_generator(SimpleNamespace(node='source.S'))
    adapter.add_probe(SimpleNamespace(node='probe.P'))
    return adapter


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestI2AdmissionIsPerPortAndPerHop(unittest.TestCase):
    """ The transit VLAN must be checked against the arrival port's own set. """

    def test_admission_is_captured_per_ingress_port(self):
        adapter = _build('ndd')
        # in.a admits 99 on port 5 and 10 on port 6 -- NOT {10,99} on both.
        self.assertEqual(adapter._in_port_vlans.get(('in.a', '5')), {'99'})
        self.assertEqual(adapter._in_port_vlans.get(('in.a', '6')), {'10'})

    def test_every_ingress_edge_is_gated_not_only_the_source_edge(self):
        adapter = _build('ndd')
        spliced, _nats, _nat_rules, _acls, _acl_rules = adapter._build_i2_faithful(
            list(adapter._edges))
        # The transit hop out.b:2 -> in.a:5 must not survive as a bare edge; it
        # has to pass an admission element first.
        self.assertNotIn("out.b 2 in.a 5", spliced)
        gated = [e for e in spliced if 'iadm' in e]
        self.assertTrue(any(e.startswith("out.b 2 ") for e in gated),
                        "the transit ingress edge carries no admission gate: %s" % gated)

    def test_a_vlan_the_arrival_port_does_not_admit_is_dropped(self):
        for engine in ('bdd', 'ndd'):
            with self.subTest(engine=engine):
                adapter = _build(engine)
                adapter.check_compliance({"probe.P": [("source.S", False, None)]})
                # "must reach" is VIOLATED: VLAN 10 is not admitted on in.a:5.
                self.assertEqual(adapter.get_compliance_results(),
                                 [("source.S", "probe.P", True, "")])


if __name__ == '__main__':
    unittest.main()
