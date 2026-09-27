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

""" A NAT's rewrite must survive rules applied to OTHER elements afterwards.

THE DEFECT THIS PINS (upstream APKeep; TODO.md item 29). A `NATElement` stores,
per input atomic predicate, the BDD its rewrite produces. `Element.forwardAPs`
carries packets onward by INTERSECTING AP-ID SETS (`retainAll`), so a stored
output only forwards if it is a member of the atomic-predicate partition --
a plain BDD node that happens to be valid intersects to nothing, and the traffic
disappears with no error.

`NATElement.updateRewriteTable()` is what registers the outputs (via
`APKeeper.addPredicate`), but upstream runs it only from
`Element.updatePortPredicateMap`, i.e. only on the element that just received a
rule. That is not when the outputs go stale. They go stale when a rule inserted
into ANY OTHER element splits or merges one of this NAT's input APs:
`updateAPSplit` / `updateAPSetMergeBatch` recompute the outputs with
`bdd.nat(...)`, producing fresh unregistered BDDs, and nothing re-registers them.

On wl_cloud the NAT rules are emitted before ~550 first-match filter rules, so
every rewrite output was stale by the end of the build. The gateway's DNAT
therefore delivered nothing: APKeep-BDD answered 53 of 64 reachable pairs where
NDD and NetPlumber both answer 59, losing exactly the six internet-sourced ones
(CLOUD_BENCH_PLAN.md 1.7.3). Silently -- a wrong verdict, not an error.

THE MODEL. A gateway DNATs one public address onto a private /24; a core routes
that /24 to a probe.

    A --> gw ---[DNAT dst 121.140.254.11:342 -> 10.0.0.0/24]--> core --> B
                                                                  \\--> C

`test_the_rewrite_survives_a_later_rule` adds one more rule, to the CORE: a
policy route for a source prefix, which cuts the gateway's input predicate in
two and sends the halves to different ports (so the batch merge cannot undo the
split). Nothing about the A->B path changes -- and before the fix, A->B went
unreachable.

TWO NETWORKS, ONE PROCESS. `Element.setBDDWrapper` is static, so constructing a
second APKeep network invalidates the first. Both are therefore built and
QUERIED in `setUpClass`, in order, and the tests assert on the recorded verdicts.
"""

import unittest

from apkeep.lib_apkeep import LibAPKeep, available
from test.backend_gate import require_or_skip

#: A `+ filter` rule body: out-port, then the 5-tuple as (lo, hi)/(addr, cisco
#: wildcard) pairs, then the priority. `null` is "any" for a port range.
_BODY = ("0 %(out)s %(plo)s %(phi)s %(src)s %(srcw)s %(spl)s %(sph)s "
         "%(dst)s %(dstw)s %(dpl)s %(dph)s %(prio)s null null null")


def _body(out, plo='0', phi='255', src='0.0.0.0', srcw='255.255.255.255',
          spl='null', sph='null', dst='0.0.0.0', dstw='255.255.255.255',
          dpl='null', dph='null', prio='100'):
    return _BODY % dict(out=out, plo=plo, phi=phi, src=src, srcw=srcw,
                        spl=spl, sph=sph, dst=dst, dstw=dstw, dpl=dpl,
                        dph=dph, prio=prio)


#: The gateway's published service: tcp/342 on one public address.
_PUBLISHED = _body('2', plo='6', phi='6', dst='121.140.254.11', dstw='0.0.0.0',
                   dpl='342', dph='342', prio='100')

_EDGES = [
    "A 1 gw 1",        # source -> gateway ingress
    "gw 2 core 1",     # gateway egress 2 (the NAT is spliced here) -> core
    "core 2 B 1",      # core egress 2 -> probe B
    "core 3 C 1",      # core egress 3 -> the policy-routed path
]

_RULES = [
    # the gateway publishes the service ...
    "+ filter gw filter " + _PUBLISHED,
    # ... and DNATs it onto the private /24 (the host bits come out free).
    "+ nat gw 2 match dst 10.0.0.0 24 filter " + _PUBLISHED,
    # the core routes the POST-rewrite destination to B.
    "+ filter core filter " + _body('2', dst='10.0.0.0', dstw='0.0.0.255',
                                    prio='100'),
]

#: One more rule, on the CORE, applied AFTER the NAT: a policy route that takes
#: one source prefix out of the published service and sends it elsewhere. It
#: splits the gateway's input predicate in two, which is the whole point; the
#: two halves leave by different ports so the end-of-update merge cannot
#: coalesce them back. In a real model this is simply "any later rule".
_LATER = ("+ filter core filter "
          + _body('3', plo='6', phi='6', src='10.1.0.0', srcw='0.0.255.255',
                  dst='121.140.254.11', dstw='0.0.0.0', dpl='342', dph='342',
                  prio='200'))


def _reaches(rules):
    """ Build the model with `rules` and answer A -> B. """
    lib = LibAPKeep()
    lib.init_in_memory("nat-rewrite", _EDGES, fwd_devices=None,
                       device_acls=None, device_nats={"gw": ["2"]},
                       device_filters=["gw", "core"],
                       bdd_table_size=1_000_000)
    lib.run(rules)
    return bool(lib.is_reachable("A", "1", "B", "1")), int(lib.ap_num())


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestNATRewriteSurvivesLaterRules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.plain, cls.plain_aps = _reaches(list(_RULES))
        cls.later, cls.later_aps = _reaches(list(_RULES) + [_LATER])

    def test_the_rewrite_delivers_when_nothing_follows_it(self):
        """ The control. With the NAT rule last, its outputs are registered by
        the update that inserted it and never disturbed again -- which is why
        the defect below hid: every small NAT test looked like this. """
        self.assertTrue(self.plain,
                        "the DNAT does not deliver even with no later rule; "
                        "this test no longer pins what it claims to")

    def test_the_rewrite_survives_a_later_rule(self):
        """ The defect. The added rule is on the CORE and says nothing about
        the A->B path; A->B must answer exactly as it did without it. """
        self.assertTrue(
            self.later,
            "a rule inserted into another element after the NAT made the "
            "rewritten traffic vanish: the NAT's rewrite outputs were "
            "recomputed as raw BDDs and never re-registered as atomic "
            "predicates, so Element.forwardAPs intersected them away")

    def test_the_later_rule_really_did_split_the_partition(self):
        """ Guards the guard: if the added rule stopped cutting the gateway's
        input predicate, the test above would pass for no reason. """
        self.assertGreater(
            self.later_aps, self.plain_aps,
            "the later rule no longer refines the atomic-predicate partition, "
            "so it no longer exercises the stale-rewrite path")


if __name__ == '__main__':
    unittest.main()
