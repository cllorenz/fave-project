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
*same* reachability, and both must match the policy oracle reachable.json
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

**WHY MORE THAN ONE WORKLOAD** (2026-09-22). This gate was `wl_ifi` only, and
that is precisely how APKeep came to over-approximate wl_up silently for months:
its in-port-qualified switch defaults were dropped by a per-device
ForwardElement (CLOUD_BENCH_PLAN.md §2.7), and nothing here compared wl_up
against a second engine -- its own APKeep tests compare BDD against NDD, which
share any approximation. A differential that covers one workload gates one
workload.

  * `wl_ifi` -- forwarding + ACLs, the original gate.
  * `wl_up` -- IPv6, packet filters, and the in-port-qualified switch defaults
    that exposed the gap. The reason it is here.
  * `wl_deltanet` -- 16 switches whose forwarding is in-port-qualified
    throughout, and the workload that made the gap visible at all.
"""

import json
import os
import unittest

from apkeep.adapter import APKeepAdapter, available as apkeep_available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip

#: The model + oracle every workload here is driven from.
_INPUT_FILES = ("topology.json", "routes.json", "sources.json",
                "policies.json", "reachable.json")


def _inputs(prefix):
    return ["%s/%s" % (prefix, name) for name in _INPUT_FILES]


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


def _matrix(engine, prefix):
    """ Drive one workload through the engine and return the base-name
    reachability matrix probe -> {sources that reach it}, self-reach excluded. """
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
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


class _Differential(unittest.TestCase):
    """ The gate itself, over whichever workload the subclass names.

    A `TestCase` rather than a bare mixin so that `assertEqual` is a real
    inherited member -- a plain mixin reads as an undefined attribute to any
    static checker, and the lint gate fails on that. It is kept out of the run
    two ways, because the two loaders skip differently: `__test__ = False` is
    what pytest honours, and the `PREFIX is None` guard is what stops a plain
    `unittest` discovery from running it against no workload.
    """

    __test__ = False

    PREFIX = None
    GENERATOR = None          # the script that produces this workload's inputs

    #: Which APKeep engines to compare. BOTH are shipped and the aggregator
    #: defaults to `ndd` (`aggregator_service.py`, `apkeep_engine='ndd'`), so a
    #: differential that ran only `bdd` -- as this file used to -- validated an
    #: engine the benchmarks do not use. Measured on wl_up: bdd 688s, ndd 4.7s
    #: for the same 137 roles and the same answer, which is why the big
    #: workload runs `ndd` alone and the cheap ones run both.
    ENGINES = ('bdd', 'ndd')

    #: Whether `reachable.json` answers the same question this asks. It does not
    #: everywhere -- see `TestBackendDifferentialUp`.
    CHECK_ORACLE = True

    @classmethod
    def setUpClass(cls):
        if cls.PREFIX is None:
            raise unittest.SkipTest("the base differential names no workload")
        from netplumber.lib_adapter import NetPlumberLibAdapter
        cls.apkeep = {
            engine: _matrix(
                APKeepAdapter(_logger(), faithful_vlan=False, engine=engine),
                cls.PREFIX)
            for engine in cls.ENGINES
        }
        cls.netplumber = _matrix(NetPlumberLibAdapter(_logger()), cls.PREFIX)
        with open("%s/reachable.json" % cls.PREFIX) as raw:
            cls.oracle = json.load(raw)

    def _diff(self, got, exp):
        d = {}
        for role in sorted(set(got) | set(exp)):
            g, e = got.get(role, set()), set(exp.get(role, []))
            if g != e:
                d[role] = {"only_a": sorted(g - e), "only_b": sorted(e - g)}
        return d

    def test_backends_agree(self):
        """ The engines compute identical reachability.

        The assertion that would have caught APKeep's wl_up over-approximation:
        two independent algorithms on one model, so an approximation in either
        shows up as a disagreement rather than as a plausible number.
        """
        for engine in self.ENGINES:
            self.assertEqual(
                self._diff(self.apkeep[engine], self.netplumber), {},
                "APKeep(%s) and NetPlumber disagree on %s"
                % (engine, self.PREFIX))

    def test_apkeep_matches_oracle(self):
        if not self.CHECK_ORACLE:
            raise unittest.SkipTest(
                "%s/reachable.json answers a different question -- see the "
                "class docstring" % self.PREFIX)
        for engine in self.ENGINES:
            self.assertEqual(
                self._diff(self.apkeep[engine], self.oracle), {},
                "APKeep(%s) differs from %s/reachable.json"
                % (engine, self.PREFIX))

    def test_netplumber_matches_oracle(self):
        if not self.CHECK_ORACLE:
            raise unittest.SkipTest(
                "%s/reachable.json answers a different question -- see the "
                "class docstring" % self.PREFIX)
        self.assertEqual(self._diff(self.netplumber, self.oracle), {},
                         "NetPlumber differs from %s/reachable.json" % self.PREFIX)


def _gate(cls):
    """ Skip unless both engines are available and the workload is generated. """
    cls = require_or_skip(
        all(os.path.isfile(f) for f in _inputs(cls.PREFIX)),
        "%s inputs not generated (run test/%s)" % (cls.PREFIX, cls.GENERATOR))(cls)
    cls = require_or_skip(
        lib_adapter.libnetplumber is not None, "libnetplumber is not built")(cls)
    return require_or_skip(
        apkeep_available(), "JPype or the APKeep jar is unavailable")(cls)


@_gate
class TestBackendDifferential(_Differential):
    """ wl_ifi: forwarding + ACLs. The original gate. """

    __test__ = True
    PREFIX = "bench/wl_ifi"
    GENERATOR = "gen_wl_ifi_inputs.sh"


@_gate
class TestBackendDifferentialDeltanet(_Differential):
    """ wl_deltanet: in-port-qualified forwarding on all 16 switches.

    The workload that exposed APKeep's per-device ForwardElement dropping the
    ingress qualification (CLOUD_BENCH_PLAN.md §2.6), and the one whose fix
    (§2.8's ingress demultiplexing) this pins.
    """

    __test__ = True
    PREFIX = "bench/wl_deltanet"
    GENERATOR = "gen_wl_deltanet_inputs.sh"


@_gate
class TestBackendDifferentialUp(_Differential):
    """ wl_up: IPv6 routers, packet filters, in-port-qualified switch defaults.

    The reason this file is no longer one workload. APKeep over-approximated
    wl_up for months -- its dmz/wifi default routes hold only on the host-facing
    ports, and a per-device ForwardElement applied them everywhere -- and
    nothing noticed, because wl_up's own APKeep tests compare BDD against NDD
    and both share the approximation (CLOUD_BENCH_PLAN.md §2.7).
    """

    __test__ = True
    PREFIX = "bench/wl_up"
    GENERATOR = "gen_wl_up_inputs.sh"

    #: `ndd` alone. Both engines were measured to give the SAME 137-role matrix
    #: and to agree with NetPlumber, but `bdd` takes 688s against `ndd`'s 4.7s
    #: -- APKeep's BDD path answers this per pair, and wl_up asks 18,769 of
    #: them. `ndd` is also what the aggregator runs by default, so this is the
    #: engine the benchmark's own numbers come from.
    ENGINES = ('ndd',)

    #: NO oracle comparison here, and this is a property of the ORACLE rather
    #: than of the engines. wl_up's policy is STATEFUL: 3,302 of its 18,811
    #: checks carry `f=related:1`, so `reachable.json` records what the policy
    #: permits under connection tracking. This differential asks an
    #: UNCONDITIONED all-pairs question, which the data plane answers more
    #: generously -- 96 roles differ, identically for both APKeep engines and
    #: for NetPlumber. Asserting it would pin a mismatch of questions, not of
    #: engines. `test_apkeep_compliance_cond.py` is what checks wl_up against
    #: its conditioned policy.
    CHECK_ORACLE = False


if __name__ == '__main__':
    unittest.main()
