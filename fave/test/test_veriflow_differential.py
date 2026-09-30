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

""" VeriFlow-FR against NetPlumber on the multi-field workloads: V3's gate.

The first differential that covers rewrites: VLAN tagging (wl_ifi, wl_i2,
wl_stanford), NAT (wl_cloud) and FaVe's own in_port/out_port metadata, set at
pre-routing and cleared at post-routing, in every router and packet filter.
Both engines are driven through the same in-process aggregator on the same
replay, and must compute the same all-pairs reachability matrix.

VeriFlow-FR slices device by device (Q22, `vf_slicing=device`), under a
budget of local ECs. A workload that exceeds it is not a pass and not a
failure of this gate but a MEASURED did-not-finish, and it is asserted as
such, with the table where it stopped (VERIFLOW_PLAN.md Q22).

Measured 2026-09-30 (VERIFLOW_PLAN.md V3), both revisit rules (Q4) alike:
  * equal to NetPlumber -- wl_ifi 54 pairs, wl_cloud 53, wl_example 6,
    wl_airtel1 210, wl_i2 61;
  * did not finish within 5e7 local ECs -- wl_stanford (out.yoza_rtr),
    wl_up (the pgf forward filter), wl_tum (its one firewall table alone
    predicts 1.74e10).

wl_i2 takes minutes per engine, so it runs only with
VERIFLOW_FULL_DIFFERENTIAL=1. The file needs FAVE_ALLOW_OUT_IFACE=1 for
wl_example and wl_tum (TODO item 13a) and runs in test.sh's group for it.

Needs libveriflow_fr, libnetplumber and the generated inputs; skips without them.
"""

import logging
import os
import unittest

from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from veriflow.adapter import VeriFlowAdapter, available

_F = {"topology": "device_topology.json", "policies": "probes.json"}

#: Local ECs one check set may slice before it counts as did-not-finish.
BUDGET = 50_000_000


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _matrix(engine, prefix, files, sources_of, probes_of, missing_of):
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix, files=files)
        sources, probes = sources_of(engine), probes_of(engine)
        fave.check_compliance({p: [[s, False, []] for s in sources] for p in probes})
    missing = missing_of(engine)
    return {_base(p): {_base(s) for s in sources
                       if (s, p) not in missing and _base(s) != _base(p)}
            for p in probes}


def veriflow_matrix(prefix, files=None, budget=BUDGET):
    engine = VeriFlowAdapter(logging.getLogger("test_veriflow_differential"), budget=budget)
    return engine, _matrix(
        engine, prefix, files,
        lambda e: sorted(g.node for g in e._generators),
        lambda e: sorted(p.node for p in e._probes),
        lambda e: {(s, p) for (s, p, _m, _c) in e.get_compliance_results()})


def netplumber_matrix(prefix, files=None):
    engine = lib_adapter.NetPlumberLibAdapter(logging.getLogger("test_veriflow_differential"))

    def missing(e):
        sid = {info[1]: name for name, info in e.generators.items()}
        pid = {info[1]: name for name, info in e.probes.items()}
        return {(sid[s], pid[d]) for (s, d, _v, _c) in e.get_compliance_results()
                if s in sid and d in pid}

    return _matrix(engine, prefix, files, lambda e: sorted(e.generators),
                   lambda e: sorted(e.probes), missing)


class _Agrees(unittest.TestCase):
    __test__ = False
    PREFIX = ""
    FILES = None

    def test_veriflow_equals_netplumber(self):
        if not os.path.isfile(os.path.join(self.PREFIX, "routes.json")):
            raise unittest.SkipTest("%s inputs not generated" % self.PREFIX)
        _engine, vf = veriflow_matrix(self.PREFIX, self.FILES)
        self.assertEqual(vf, netplumber_matrix(self.PREFIX, self.FILES))


def _gate(cls):
    cls = require_or_skip(lib_adapter.libnetplumber is not None,
                          "libnetplumber is not built")(cls)
    return require_or_skip(available(), "libveriflow_fr is not built")(cls)


@_gate
class TestIfi(_Agrees):
    """ A router pipeline: ACLs, VLAN tagging, metadata set and cleared. """
    __test__ = True
    PREFIX = "bench/wl_ifi"


@_gate
class TestCloud(_Agrees):
    """ NAT: a source set exactly, a destination set to a subnet. """
    __test__ = True
    PREFIX = "bench/wl_cloud"


@_gate
class TestExample(_Agrees):
    """ A packet-filter pipeline: stateful filters and FaVe's metadata. """
    __test__ = True
    PREFIX = "bench/wl_example"


@_gate
@require_or_skip(os.environ.get("VERIFLOW_FULL_DIFFERENTIAL") == "1",
                 "wl_i2 takes minutes per engine: set VERIFLOW_FULL_DIFFERENTIAL=1")
class TestI2(_Agrees):
    """ VLAN tagging on a 77k-rule mesh: 61 pairs, measured equal to NetPlumber. """
    __test__ = True
    PREFIX = "bench/wl_i2/i2-json"
    FILES = _F


@_gate
class TestTumDidNotFinish(unittest.TestCase):
    """ wl_tum's single firewall table explodes into range ECs (Q22): the check
    stops, unfinished, naming that table -- a measured outcome, not a pass. """

    def test_stops_at_the_firewall_table(self):
        from util.barrier import BarrierError
        if not os.path.isfile("bench/wl_tum/routes.json"):
            raise unittest.SkipTest("wl_tum inputs not generated")
        with self.assertRaisesRegex(BarrierError, r"fw\.tum\.forward_filter.*alone would slice"):
            veriflow_matrix("bench/wl_tum")


if __name__ == '__main__':
    unittest.main()
