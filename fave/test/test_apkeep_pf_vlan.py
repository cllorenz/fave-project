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

""" A packet filter's ingress and egress VLAN tags -- `svlan` (`-i eth1.<v>`)
and `dvlan` (`-o eth1.<v>`) -- as header fields of BDD-APKeep, NDD-APKeep and
NDD-Flood (TODO.md item 54; owner, 2026-10-14: VLANs are genuine header fields).

Until then the adapter's packet-filter path dropped both without a word, so a
rule bound to one VLAN acted on all of them. Found with wl_tum's derived policy;
shown on a minimal firewall where both APKeep engines lost reachability that
NetPlumber, VeriFlow-FR and iptables have.

Layout (after `flags` at slot 19):

    + filter <dev> filter 0 <out> ... <prio> [vlan] [related] [flags] [svlan] [dvlan]

**Absolute verdicts per engine, not only a differential.** A field that no
engine carries is invisible to a differential (test_apkeep_tcp_flags.py records
how that was measured), so each engine is asked on its own: the control (an
untagged drop takes everything), a tag-bound drop that leaves the other tags
through, and a source seeded with that tag that it does drop.
"""

import json
import logging
import os
import shutil
import tempfile
import unittest

from apkeep.adapter import (APKeepAdapter, _filter_rule_string,
                            _is_acceptall_filter_rule)
from apkeep.lib_apkeep import LibAPKeep, available as bdd_available
from apkeep.lib_ndd import LibNDD, available as ndd_available
from test.backend_gate import require_or_skip

_EDGES = ["src p1 sf in", "sf sfpass fw p1", "fw p2 dst p1"]


def _rule(dev, out, prio, svlan="null", dvlan="null"):
    return ("+ filter %s filter 0 %s 0 255 0.0.0.0 255.255.255.255 null null "
            "0.0.0.0 255.255.255.255 null null %d null null null %s %s"
            % (dev, out, prio, svlan, dvlan))


def _rules(drop_svlan, drop_dvlan, seed_svlan="null", seed_dvlan="null"):
    """ A source seed, then a tag-bound DROP in front of an accept-all forward.
    Higher priority wins. Reachability is existential, so a drop that keeps
    other tags leaves the path open; one that ignores its tag closes it. """
    return [_rule("sf", "sfpass", 1000, seed_svlan, seed_dvlan),
            _rule("fw", "__drop__", 2000, drop_svlan, drop_dvlan),
            _rule("fw", "p2", 1000)]


def _ndd(*args):
    engine = LibNDD()
    engine.build(_rules(*args), _EDGES)
    return bool(engine.is_reachable("src", "p1", "dst", "p1"))


def _apkeep(backend, *args):
    lib = LibAPKeep(backend=backend)
    lib.init_in_memory("pfvlan", _EDGES, device_filters=["sf", "fw"])
    lib.run(_rules(*args))
    return bool(lib.is_reachable("src", "p1", "dst", "p1"))


class TestTheRuleStringCarriesTheTags(unittest.TestCase):

    def test_the_tags_land_in_slots_20_and_21(self):
        rule = _filter_rule_string('d', 'p2', None, None, None, None, None,
                                   None, 1, svlan=5, dvlan=7).split()
        self.assertEqual((rule[20], rule[21]), ('5', '7'))

    def test_absent_tags_leave_the_slots_null(self):
        rule = _filter_rule_string('d', 'p2', None, None, None, None, None,
                                   None, 1).split()
        self.assertEqual((rule[20], rule[21]), ('null', 'null'))

    def test_a_tag_qualified_pass_through_is_not_an_identity(self):
        for tags in ({'svlan': 5}, {'dvlan': 7}):
            rule = _filter_rule_string('d', 'p2', None, None, None, None, None,
                                       None, 1, **tags)
            self.assertFalse(_is_acceptall_filter_rule(rule.split()), tags)


class _Verdicts(unittest.TestCase):
    """ The same five questions for every engine. A TestCase, so pylint can
    follow it; skipped as the base itself. """

    def setUp(self):
        if type(self) is _Verdicts:  # pylint: disable=unidiomatic-typecheck
            self.skipTest("the base of the per-engine classes")

    def ask(self, *args):
        raise NotImplementedError

    def test_an_untagged_drop_takes_everything(self):
        self.assertFalse(self.ask("null", "null"))

    def test_a_drop_bound_to_one_ingress_tag_leaves_the_others(self):
        self.assertTrue(self.ask("5", "null"))

    def test_a_drop_bound_to_one_egress_tag_leaves_the_others(self):
        self.assertTrue(self.ask("null", "7"))

    def test_a_source_on_that_ingress_tag_is_dropped(self):
        self.assertFalse(self.ask("5", "null", "5", "null"))
        self.assertTrue(self.ask("5", "null", "6", "null"))

    def test_a_source_tagged_for_that_egress_is_dropped(self):
        self.assertFalse(self.ask("null", "7", "null", "7"))
        self.assertTrue(self.ask("null", "7", "null", "8"))


@require_or_skip(bdd_available(), "JPype or the APKeep jar is unavailable")
class TestBddAPKeep(_Verdicts):
    def ask(self, *args):
        return _apkeep('bdd', *args)


@require_or_skip(bdd_available() and ndd_available(), "the APKeep or NDD jar is unavailable")
class TestNddAPKeep(_Verdicts):
    def ask(self, *args):
        return _apkeep('ndd', *args)


@require_or_skip(ndd_available(), "the NDD jar is unavailable")
class TestNddFlood(_Verdicts):
    def ask(self, *args):
        return _ndd(*args)


_RULESET = """iptables -P FORWARD DROP
iptables -A FORWARD -i eth1.5 -s 10.0.0.0/8 -j DROP
iptables -A FORWARD -o eth1.7 -d 192.0.2.0/24 -j DROP
iptables -A FORWARD -j ACCEPT
"""

#: source -> reachable, as iptables decides (every source enters on eth1)
_EXPECTED = {
    'v5': False,      # -i eth1.5 from 10/8: dropped
    'v6': True,       # same source on VLAN 6: the drop is VLAN 5's
    'to7': False,     # routed out eth1.7 into 192.0.2/24: dropped
    'to8': True,      # the same destination out eth1.8
    'src10': True,    # no tag: arrives on some VLAN, not only on 5
    'dst192': True,   # no tag: leaves by some VLAN, not only by 7
}

_SOURCES = {
    'v5': ["svlan=5", "ipv4_src=10.1.1.1/32"],
    'v6': ["svlan=6", "ipv4_src=10.1.1.1/32"],
    'to7': ["ipv4_src=172.16.0.1/32", "ipv4_dst=192.0.2.1/32", "dvlan=7"],
    'to8': ["ipv4_src=172.16.0.1/32", "ipv4_dst=192.0.2.1/32", "dvlan=8"],
    'src10': ["ipv4_src=10.1.1.1/32"],
    'dst192': ["ipv4_src=172.16.0.1/32", "ipv4_dst=192.0.2.1/32"],
}


def _workload(tmp, in_port='fw.eth1_ingress'):
    with open(os.path.join(tmp, 'ruleset'), 'w') as out:
        out.write(_RULESET)
    devices = [["source.%s" % n, "generator",
                (["in_port=%s" % in_port] if in_port else []) + f]
               for n, f in _SOURCES.items()]
    files = {
        'topology.json': {'devices': [["fw", "packet_filter", ["eth0", "eth1"], "10.0.0.1",
                                       os.path.join(tmp, 'ruleset')]], 'links': []},
        'routes.json': [],
        'sources.json': {'devices': devices,
                         'links': [[d[0] + ".1", "fw.forward_filter_in", True] for d in devices]},
        'policies.json': {'devices': [["probe.acc", "probe", "existential", None, None, None, None]],
                          'links': [["fw.forward_filter_accept", "probe.acc.1", False]]},
    }
    for name, content in files.items():
        with open(os.path.join(tmp, name), 'w') as out:
            json.dump(content, out)


def _ask(engine, prefix):
    from util.in_process_driver import InProcessFaVe
    from util import incremental as inc
    checks = [inc.Check('s=source.%s && EF p=probe.acc' % n) for n in _SOURCES]
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        violated = inc.VerdictCache(fave, engine, checks).full()
    return {c.source[len('source.'):]: not violated[c.line] for c in checks}


class _ThroughFaVe(unittest.TestCase):
    """ The minimal firewall end to end: iptables -> FaVe's model -> the
    adapter -> the engine, every source entering on eth1 (`in_port`, accepted
    because fw has no routing and all its qualifiers name eth1). """

    engine = None

    def setUp(self):
        if self.engine is None:
            self.skipTest("the base of the per-engine classes")
        self.tmp = tempfile.mkdtemp(prefix='pf_vlan_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make(self):
        return APKeepAdapter(logging.getLogger('test_pf_vlan'), engine=self.engine)

    def test_the_verdicts_iptables_gives(self):
        _workload(self.tmp)
        self.assertEqual(_ask(self.make(), self.tmp), _EXPECTED)

    def test_an_in_port_the_qualifiers_do_not_name_is_refused(self):
        from util.barrier import BarrierError
        _workload(self.tmp, in_port='fw.eth0_ingress')
        with self.assertRaisesRegex(BarrierError, 'in_port'):
            _ask(self.make(), self.tmp)


@require_or_skip(bdd_available(), "JPype or the APKeep jar is unavailable")
class TestBddAPKeepThroughFaVe(_ThroughFaVe):
    engine = 'bdd'


@require_or_skip(bdd_available() and ndd_available(), "the APKeep or NDD jar is unavailable")
class TestNddAPKeepThroughFaVe(_ThroughFaVe):
    engine = 'ndd-apkeep'


@require_or_skip(ndd_available(), "the NDD jar is unavailable")
class TestNddFloodThroughFaVe(_ThroughFaVe):
    engine = 'ndd-flood'


if __name__ == '__main__':
    unittest.main()
