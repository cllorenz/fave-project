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

""" A packet may pass the same table twice: router on a stick (VERIFLOW_PLAN.md
Q4, TODO item 33).

    host A (VLAN 10) -> sw -> rtr (VLAN 10 -> 20) -> sw, SAME table -> host B

Delivery requires crossing `sw`'s one table twice, with different headers. A
genuine loop is the control: `rtr` returns VLAN 10 unchanged, and `sw` sends
VLAN 10 back up, so the packet circles and never reaches B.

    ground truth           stick: reached   loop: not reached
    VeriFlow-FR, state     reached           not reached     (the thesis's rule)
    ad6                    reached           not reached     (SAT, independent)
    VeriFlow-FR, path      NOT reached       not reached     (NetPlumber's rule)
    NetPlumber             NOT reached       not reached     -- KNOWN DEFECT
    APKeep, bdd and ndd    reached           REACHED         -- KNOWN DEFECT

The correct engines are asserted correct. The two defects are PINNED as they
are measured (2026-09-30), so that a fix fails this test and is seen rather
than silently changing a number elsewhere:

  * NetPlumber stops a flow whose path revisits a table, whatever its header
    (`net_plumber/FAVE_CHANGES.md` §6, unchanged from upstream): it
    UNDER-approximates reachability wherever a packet legitimately passes a
    table twice;
  * APKeep answers "reached" on both networks, with either engine and either
    VLAN mode: its answer here does not depend on the switches' VLAN matches,
    so the stick's "reached" is coincidental and the loop's is a false
    positive. The cause is not yet verified.

Built through FaVe's real input path (JSON replayed by the in-process
aggregator), so every engine sees what a workload gives it. Needs the native
engines; each part skips without its own.
"""

import json
import logging
import os
import tempfile
import unittest

_TOPOLOGY = {
    "devices": [["sw", "switch", ["1", "2", "3", "4"], {"sw": 1}, {}],
                ["rtr", "switch", ["1", "2"], {"rtr": 2}, {}]],
    "links": [["sw.3", "rtr.1", False], ["rtr.2", "sw.4", False]]}
_SOURCES = {"devices": [["source.a", "generator", ["vlan=10", "ipv4_dst=10.0.2.0/24"]]],
            "links": [["source.a.1", "sw.1", True]]}
_POLICIES = {"devices": [["probe.b", "probe", "existential", None, None, None, None]],
             "links": [["sw.2", "probe.b.1", False]]}

STICK = [
    ["sw", 1, 1, ["vlan=10"], ["fd=sw.3"], ["sw.1"]],
    ["rtr", 1, 1, ["vlan=10", "ipv4_dst=10.0.2.0/24"], ["rw=vlan:20", "fd=rtr.2"], ["rtr.1"]],
    ["sw", 1, 2, ["vlan=20"], ["fd=sw.2"], ["sw.4"]],
]
LOOP = [
    ["sw", 1, 1, ["vlan=10"], ["fd=sw.3"], ["sw.1"]],
    ["rtr", 1, 1, ["vlan=10", "ipv4_dst=10.0.2.0/24"], ["fd=rtr.2"], ["rtr.1"]],
    ["sw", 1, 2, ["vlan=10"], ["fd=sw.3"], ["sw.4"]],
    ["sw", 1, 3, ["vlan=20"], ["fd=sw.2"], ["sw.4"]],
]


def _write(routes):
    d = tempfile.mkdtemp(prefix="fave_stick_")
    for name, obj in (("topology", _TOPOLOGY), ("routes", routes),
                      ("sources", _SOURCES), ("policies", _POLICIES)):
        with open(os.path.join(d, name + ".json"), "w") as out:
            json.dump(obj, out)
    return d


def _reached(engine, prefix, sources_of, probes_of, missing_of):
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        fave.check_compliance({p: [[s, False, []] for s in sources_of(engine)]
                               for p in probes_of(engine)})
    return ("source.a", "probe.b") not in missing_of(engine)


def _log():
    return logging.getLogger("test_revisit_router_on_a_stick")


def veriflow(prefix, revisit):
    from veriflow.adapter import VeriFlowAdapter
    return _reached(VeriFlowAdapter(_log(), revisit=revisit), prefix,
                    lambda e: sorted(g.node for g in e._generators),
                    lambda e: sorted(p.node for p in e._probes),
                    lambda e: {(s, p) for (s, p, _m, _c) in e.get_compliance_results()})


def netplumber(prefix):
    from netplumber.lib_adapter import NetPlumberLibAdapter

    def missing(e):
        sid = {i[1]: n for n, i in e.generators.items()}
        pid = {i[1]: n for n, i in e.probes.items()}
        return {(sid[s], pid[d]) for (s, d, _v, _c) in e.get_compliance_results()
                if s in sid and d in pid}

    return _reached(NetPlumberLibAdapter(_log()), prefix, lambda e: sorted(e.generators),
                    lambda e: sorted(e.probes), missing)


def apkeep(prefix, engine):
    from apkeep.adapter import APKeepAdapter
    return _reached(APKeepAdapter(_log(), faithful_vlan=True, engine=engine), prefix,
                    lambda e: sorted(e._generators), lambda e: sorted(e._probes),
                    lambda e: {(s, p) for (s, p, _mr, _c) in e.get_compliance_results()})


def ad6(prefix):
    from ad6.adapter import Ad6Adapter
    return _reached(Ad6Adapter(_log()), prefix,
                    lambda e: sorted(getattr(e, "_generators", {})),
                    lambda e: sorted(getattr(e, "_probes", {})),
                    lambda e: {(s, p) for (s, p, _mr, _c) in e.get_compliance_results()})


class TestRouterOnAStick(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.stick, cls.loop = _write(STICK), _write(LOOP)

    def _need(self, module_available, what):
        if not module_available:
            raise unittest.SkipTest("%s is not built" % what)

    def test_veriflow_state_is_right_on_both(self):
        from veriflow.adapter import available
        self._need(available(), "libveriflow_fr")
        self.assertTrue(veriflow(self.stick, "state"))
        self.assertFalse(veriflow(self.loop, "state"))

    def test_ad6_is_right_on_both(self):
        self.assertTrue(ad6(self.stick))
        self.assertFalse(ad6(self.loop))

    def test_path_rule_loses_the_stick_as_netplumber_does(self):
        from veriflow.adapter import available
        self._need(available(), "libveriflow_fr")
        self.assertFalse(veriflow(self.stick, "path"))
        self.assertFalse(veriflow(self.loop, "path"))

    def test_netplumber_known_defect_under_approximates_the_stick(self):
        from netplumber.lib_adapter import libnetplumber
        self._need(libnetplumber is not None, "libnetplumber")
        self.assertFalse(netplumber(self.stick),
                         "NetPlumber now reaches B across the stick: TODO item 33 fixed? "
                         "Update this test and the item.")
        self.assertFalse(netplumber(self.loop))

    def test_netplumber_reports_the_loops_that_truncate(self):
        # NetPlumber stops a flow exactly where it fires its loop callback, so
        # the count of loop reports is what the item-33 count relies on: zero
        # reports on a workload proves the table rule truncated nothing there.
        # Here it reports on BOTH networks -- the stick's is the false one.
        from netplumber.lib_adapter import NetPlumberLibAdapter, libnetplumber
        self._need(libnetplumber is not None, "libnetplumber")
        from util.in_process_driver import InProcessFaVe
        for prefix in (self.stick, self.loop):
            eng = NetPlumberLibAdapter(_log())
            with InProcessFaVe(eng) as fave:
                fave.replay(prefix)
            self.assertGreater(eng.loop_reports(), 0, prefix)

    def test_apkeep_known_defect_over_approximates_the_loop(self):
        from apkeep.adapter import available
        self._need(available(), "APKeep (JPype + jar)")
        for engine in ("bdd", "ndd"):
            self.assertTrue(apkeep(self.stick, engine))
            self.assertTrue(apkeep(self.loop, engine),
                            "APKeep(%s) no longer reaches B in the loop: TODO item 33 "
                            "fixed? Update this test and the item." % engine)


if __name__ == '__main__':
    unittest.main()
