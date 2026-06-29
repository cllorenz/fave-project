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

""" NetPlumber-vs-APKeep reachability differential (APKEEP_BACKEND.md, P5).

The correctness gate for the second backend: the two engines must compute the
*same* wl_ifi reachability, and both must match the policy oracle reachable.json
(item 8's differential-oracle idea, applied between backends). Both are driven
through the identical in-process path (InProcessFaVe over an AggregatorService),
so the comparison is of the engines, not of two packagings.

Each backend answers an all-pairs "must reach" compliance query; a recorded
violation means the source does NOT reach the probe, so the reachable set is the
complement. APKeep does this via per-pair port reachability; NetPlumber via its
source-flow compliance (NetPlumber<>::check_compliance inspects each probe's
incoming source flows) -- two independent algorithms that must agree.

Intra-switch self-reach (source.X -> probe.X) is excluded: it never traverses
the router, and the policy matrix never asks about it.
"""

import json
import os
import unittest

from apkeep.adapter import APKeepAdapter, available as apkeep_available
from netplumber import lib_adapter

_PREFIX = "bench/wl_ifi"
_INPUTS = ["%s/%s" % (_PREFIX, f) for f in
           ("topology.json", "routes.json", "sources.json", "policies.json", "reachable.json")]


def _logger():
    import logging
    log = logging.getLogger("test_backend_differential")
    log.setLevel(logging.WARNING)
    return log


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _names(engine):
    """ (sorted source names, sorted probe names) -- APKeep buffers them under
    _generators/_probes, NetPlumberAdapter under generators/probes. """
    if isinstance(engine, APKeepAdapter):
        return sorted(engine._generators), sorted(engine._probes)
    return sorted(engine.generators), sorted(engine.probes)


def _not_reached(engine):
    """ The (source, probe) NAME pairs an all-pairs must-reach query flagged as
    violations == not reached. APKeep reports names; NetPlumber reports node ids
    (mapped back via generators/probes). """
    results = engine.get_compliance_results()
    if isinstance(engine, APKeepAdapter):
        return {(s, p) for (s, p, _mr, _c) in results}
    sid = {info[1]: name for name, info in engine.generators.items()}
    pid = {info[1]: name for name, info in engine.probes.items()}
    return {(sid[s], pid[d]) for (s, d, _v, _c) in results if s in sid and d in pid}


def _matrix(engine):
    """ Drive wl_ifi through the engine and return the base-name reachability
    matrix probe -> {sources that reach it}, self-reach excluded. """
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        sources, probes = _names(engine)
        rules = {p: [[s, False, []] for s in sources] for p in probes}
        fave.check_compliance(rules)
    not_reached = _not_reached(engine)
    return {
        _base(p): set(
            _base(s) for s in sources
            if (s, p) not in not_reached and _base(s) != _base(p)
        )
        for p in probes
    }


@unittest.skipUnless(apkeep_available(), "JPype or the APKeep jar is unavailable")
@unittest.skipUnless(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
@unittest.skipUnless(all(os.path.isfile(f) for f in _INPUTS),
                     "wl_ifi inputs not generated (run test/gen_wl_ifi_inputs.sh)")
class TestBackendDifferential(unittest.TestCase):
    """ FaVe+APKeep and FaVe+NetPlumber must agree on wl_ifi reachability and
    both match reachable.json. """

    @classmethod
    def setUpClass(cls):
        from netplumber.lib_adapter import NetPlumberLibAdapter
        cls.apkeep = _matrix(APKeepAdapter(_logger()))
        cls.netplumber = _matrix(NetPlumberLibAdapter(_logger()))
        with open("%s/reachable.json" % _PREFIX) as raw:
            cls.oracle = json.load(raw)

    def _diff(self, got, exp):
        d = {}
        for role in sorted(set(got) | set(exp)):
            g, e = got.get(role, set()), set(exp.get(role, []))
            if g != e:
                d[role] = {"only_a": sorted(g - e), "only_b": sorted(e - g)}
        return d

    def test_backends_agree(self):
        """ The two engines compute identical reachability. """
        self.assertEqual(self._diff(self.apkeep, self.netplumber), {},
                         "APKeep and NetPlumber disagree")

    def test_apkeep_matches_oracle(self):
        self.assertEqual(self._diff(self.apkeep, self.oracle), {},
                         "APKeep differs from reachable.json")

    def test_netplumber_matches_oracle(self):
        self.assertEqual(self._diff(self.netplumber, self.oracle), {},
                         "NetPlumber differs from reachable.json")


if __name__ == '__main__':
    unittest.main()
