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

""" VeriFlow-FR on the Delta-net airtel workloads: VERIFLOW_PLAN.md V1's gates.

  * **The differential** (§8). VeriFlow-FR's reachability matrix equals the
    workload's `reachable.json` AND NetPlumber's, both driven through the same
    in-process aggregator on the same replay -- so an error in either shows as
    a disagreement, not as a plausible number.

  * **The LPM guard** (`CLOUD_BENCH_PLAN.md` §3). The matrix cannot see
    longest-prefix match on these workloads: inverted so the SHORTEST prefix
    wins, NetPlumber still reports 0 violations, because a misrouted prefix
    leaves its siblings arriving (`test_deltanet_lpm.py`). So the guard asks
    the engine directly: for nested prefixes at one switch that forward
    differently, the packet at the inner prefix's first address is decided by
    the inner rule. And it shows it can fail: with the adapter told to invert
    LPM (a switch that exists for this guard only), the same check fails.

Needs the libveriflow_fr and libnetplumber builds and the generated airtel
inputs (test/gen_deltanet_inputs.sh); skips without them.
"""

import json
import logging
import os
import unittest

from typing import Optional

from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from veriflow.adapter import VeriFlowAdapter, available

_FILES = ("topology.json", "routes.json", "sources.json", "policies.json",
          "reachable.json")


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _logger():
    log = logging.getLogger("test_veriflow_airtel")
    log.setLevel(logging.WARNING)
    return log


def _drive(engine, prefix, sources_of, probes_of, not_reached_of):
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        sources, probes = sources_of(engine), probes_of(engine)
        fave.check_compliance({p: [[s, False, []] for s in sources] for p in probes})
    missing = not_reached_of(engine)
    return {
        _base(p): {_base(s) for s in sources
                   if (s, p) not in missing and _base(s) != _base(p)}
        for p in probes
    }


def _veriflow_matrix(prefix, **kwargs):
    engine = VeriFlowAdapter(_logger(), **kwargs)
    matrix = _drive(
        engine, prefix,
        lambda e: sorted(g.node for g in e._generators),
        lambda e: sorted(p.node for p in e._probes),
        lambda e: {(s, p) for (s, p, _mr, _c) in e.get_compliance_results()})
    return engine, matrix


def _netplumber_matrix(prefix):
    engine = lib_adapter.NetPlumberLibAdapter(_logger())

    def not_reached(e):
        sid = {info[1]: name for name, info in e.generators.items()}
        pid = {info[1]: name for name, info in e.probes.items()}
        return {(sid[s], pid[d]) for (s, d, _v, _c) in e.get_compliance_results()
                if s in sid and d in pid}

    return _drive(engine, prefix, lambda e: sorted(e.generators),
                  lambda e: sorted(e.probes), not_reached)


def _nested_pairs(engine):
    """ (table, in_port, outer rule, inner rule): each prefix and the nearest
    shorter prefix containing it, at one switch and ingress port, where the two
    forward differently -- the pairs LPM decides. Every rule on these workloads
    is qualified by an ingress port, so nesting is only meaningful per port. """
    by_key = {}
    for r in engine.ir.rules:
        if not r.consume:
            by_key.setdefault((r.table, r.in_port), {})[r.match] = r
    pairs = []
    for (table, in_port), rules in sorted(by_key.items()):
        for match, inner in sorted(rules.items()):
            fixed = match.index('x') if 'x' in match else len(match)
            for length in range(fixed - 1, -1, -1):
                outer = rules.get(match[:length] + 'x' * (len(match) - length))
                if outer is not None:
                    if outer.out_ports != inner.out_ports:
                        pairs.append((table, in_port, outer, inner))
                    break
    return pairs


def _lpm_violations(engine, pairs):
    bad = 0
    for table, in_port, _outer, inner in pairs:
        point = inner.match.replace('x', '0')
        if engine.net.decide_point(point, table, in_port) != inner.id:
            bad += 1
    return bad


class _Airtel(unittest.TestCase):
    __test__ = False
    PREFIX: Optional[str] = None

    @classmethod
    def setUpClass(cls):
        if cls.PREFIX is None:
            raise unittest.SkipTest("no workload")
        cls.engine, cls.veriflow = _veriflow_matrix(cls.PREFIX)
        cls.netplumber = _netplumber_matrix(cls.PREFIX)
        with open("%s/reachable.json" % cls.PREFIX) as raw:
            cls.oracle = {k: set(v) for k, v in json.load(raw).items()}

    def test_matches_the_oracle(self):
        self.assertEqual(self.veriflow, self.oracle)

    def test_matches_netplumber(self):
        self.assertEqual(self.veriflow, self.netplumber)

    #: Nested prefixes that forward differently, per (switch, ingress port).
    #: MEASURED 2026-09-29 on both traces: 53 nested pairs, 13 of them with
    #: different next hops -- few, because every rule is port-qualified. The
    #: guard's size is stated so a translation that loses pairs fails here.
    NESTED_DIFFERENT = 13

    def test_lpm_guard_sees_longest_prefix(self):
        pairs = _nested_pairs(self.engine)
        self.assertEqual(len(pairs), self.NESTED_DIFFERENT)
        self.assertEqual(_lpm_violations(self.engine, pairs), 0)

    def test_lpm_guard_can_fail(self):
        # Inverted, the SHORTER prefix decides every one of the pairs.
        inverted, _matrix = _veriflow_matrix(self.PREFIX, invert_lpm=True)
        pairs = _nested_pairs(inverted)
        self.assertEqual(_lpm_violations(inverted, pairs), len(pairs))

    #: Delta-net's graph for this snapshot: 158 edges on airtel1 (the §4.3.2
    #: query count, bench/deltanet/TRACES.md), 155 on airtel2.
    EDGES: Optional[int] = None

    def test_node_edges_are_delta_nets(self):
        from veriflow.translate import node_edges
        edges = node_edges(self.engine.ir)
        self.assertEqual(len(edges), self.EDGES)
        self.assertEqual(len({(t, p) for (t, p, _to) in edges} |
                             {(self.engine.ir.port_table[to], to) for (_t, _p, to) in edges}),
                         68)

    def test_stamps(self):
        stamps = self.engine.ir.stamps
        self.assertEqual(stamps["impl"], "reimpl-literature")
        self.assertEqual(stamps["vf_field_order"], ["packet.ipv4.destination"])
        self.assertEqual(stamps["vf_inport_expansion"], round(42000 / 39500, 3))


def _gate(cls):
    cls = require_or_skip(
        all(os.path.isfile("%s/%s" % (cls.PREFIX, f)) for f in _FILES),
        "%s inputs not generated (run test/gen_deltanet_inputs.sh)" % cls.PREFIX)(cls)
    cls = require_or_skip(lib_adapter.libnetplumber is not None,
                          "libnetplumber is not built")(cls)
    return require_or_skip(available(), "libveriflow_fr is not built "
                           "(veriflow_fr/python/build_libveriflow_fr.sh)")(cls)


@_gate
class TestVeriFlowAirtel1(_Airtel):
    __test__ = True
    PREFIX = "bench/wl_airtel1"
    EDGES = 158


@_gate
class TestVeriFlowAirtel2(_Airtel):
    __test__ = True
    PREFIX = "bench/wl_airtel2"
    EDGES = 155


if __name__ == '__main__':
    unittest.main()
