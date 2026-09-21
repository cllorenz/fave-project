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

""" ad6-vs-NetPlumber reachability on wl_cloud, anchored to the dataset.

THE GAP THIS CLOSES. ad6's masked rewrite was implemented backwards -- the
don't-care bits of a rewrite VALUE were framed from the incoming header instead
of freed -- and nothing in the tree noticed. Every piece was individually
correct and individually tested: `cloud_preparation` emitted the right rule,
`translate` emitted the right XML, and `_CreateMutationConstraints` did exactly
what its own unit test said it should. What was wrong was the SEMANTIC CHOICE,
and a unit test cannot catch that, because it is written from the same
misunderstanding as the code.

What caught it was disagreement: NetPlumber said the internet reaches six hosts
and ad6 said it reaches none. So the guard is a differential, on the workload
where the third-party verdicts live.

UNCONDITIONED, DELIBERATELY. Every check is a plain pair with no `cond`, which
keeps ad6's query-seeding limits (`fave_bridge._SUPPORTED_COND_FIELDS`) out of
the comparison -- this is about the model and the encoding. It also happens to
be exactly query 01, which carries no constraint of its own.

AND ANCHORED, not merely a consensus. Agreement between two engines that broke
the same way would be green, so the oracle-backed cells are asserted against
the dataset's own verdicts as well (CLOUD_BENCH_PLAN.md §1.8, §1.9.0).
"""

import json
import logging
import os
import unittest

from netplumber import lib_adapter
from test.backend_gate import require_or_skip

_PREFIX = 'bench/wl_cloud'
_INPUTS = ['%s/%s' % (_PREFIX, f) for f in
           ('topology.json', 'routes.json', 'sources.json', 'policies.json',
            'mapping.json')]

#: The cells the dataset itself states a verdict for, unconditioned.
#:
#: q01/q03 are `sat` and are the two this test exists for. q02 is `unsat` and
#: is the control that keeps the assertion from being satisfiable by an engine
#: that simply says yes to everything. q04's instance forbids only the ports
#: OTHER than 331, and q05/q06 constrain a port, so their unconditioned cells
#: are supersets and state nothing here -- they are deliberately absent rather
#: than asserted loosely.
_ORACLE = {
    ('internet', 'dc1_leaf5_host5'): True,       # q01, sat
    ('internet', 'dc2_leaf7_host6'): False,      # q02, unsat
    ('internet', 'dc1_leaf0_host20'): True,      # q03, sat
}


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _matrix(engine):
    """ probe -> {source: reachable}, over every generator and probe, with no
    condition on any check. """
    from util.in_process_driver import InProcessFaVe

    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        sources = sorted(getattr(engine, '_generators', None) or engine.generators)
        probes = sorted(getattr(engine, '_probes', None) or engine.probes)
        fave.check_compliance(
            {p: [[s, False, []] for s in sources] for p in probes})

    results = engine.get_compliance_results()
    if hasattr(engine, 'generators') and not hasattr(engine, '_generators'):
        sid = {i[1]: n for n, i in engine.generators.items()}
        pid = {i[1]: n for n, i in engine.probes.items()}
        missed = {(sid[s], pid[d]) for (s, d, _v, _c) in results
                  if s in sid and d in pid}
    else:
        missed = {(s, p) for (s, p, _mr, _c) in results}

    return {(_base(s), _base(p)): (s, p) not in missed
            for p in probes for s in sources}


def _logger(name):
    log = logging.getLogger(name)
    log.setLevel(logging.ERROR)
    return log


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_cloud inputs not generated (run test/gen_wl_cloud_inputs.sh)")
class TestAd6CloudDifferential(unittest.TestCase):
    """ Two engines, one model, and a dataset that predates both. """

    @classmethod
    def setUpClass(cls):
        from ad6.adapter import Ad6Adapter

        mapping = json.load(open('%s/mapping.json' % _PREFIX))
        cls.np = _matrix(lib_adapter.NetPlumberLibAdapter(
            _logger('cloud_diff_np'), mapping=mapping))
        cls.ad6 = _matrix(Ad6Adapter(_logger('cloud_diff_ad6')))

    def test_the_two_engines_agree_on_every_pair(self):
        """ The differential proper. A cell where they differ is a real defect
        in one of them -- both are driven through the identical in-process path
        over the identical generated model, so nothing else can move. """
        self.assertEqual(sorted(self.np), sorted(self.ad6),
                         "the two engines did not even see the same endpoints")

        differing = {k: (self.np[k], self.ad6[k])
                     for k in self.np if self.np[k] != self.ad6[k]}
        self.assertEqual(
            differing, {},
            "netplumber and ad6 disagree on %d of %d pairs (np, ad6)"
            % (len(differing), len(self.np)))

    def test_both_engines_match_the_dataset_where_it_speaks(self):
        """ The anchor. Two engines agreeing is not evidence they are right --
        the defect this guards against would have been invisible to a pure
        consensus if it had been in the shared model rather than in one engine.
        These three cells come from outside this repository. """
        for pair, expected in _ORACLE.items():
            self.assertEqual(self.np[pair], expected,
                             "netplumber contradicts the oracle at %s" % (pair,))
            self.assertEqual(self.ad6[pair], expected,
                             "ad6 contradicts the oracle at %s" % (pair,))

    def test_the_internet_reaches_hosts_through_the_NAT(self):
        """ The regression itself, stated as its own property so a failure
        names the cause rather than a cell count.

        Every internet-sourced path crosses the gateway's DNAT, which rewrites
        the destination to a SUBNET. Framing that rewrite's don't-care bits
        instead of freeing them collapses the subnet to the single host implied
        by the matched /32, and the whole row goes unreachable. """
        reached = sorted(p for (s, p), ok in self.ad6.items()
                         if s == 'internet' and ok and p != 'internet')
        self.assertGreater(
            len(reached), 1,
            "ad6 has the internet reaching %s. A DNAT to a subnet must reach "
            "more than one host; one (or none) is the signature of a rewrite "
            "whose don't-care bits were preserved instead of freed." % reached)
