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

""" The port-free reading of a Delta-net trace, and the walk that states its
matrix (CLOUD_BENCH_PLAN.md §2.15, `wl_berkeley`).

On a four-router trace built to have the two effects `wl_berkeley` was found to
have -- small enough to work out by hand, and worked out in the docstring of
`_TRACE` so that the expectation was written before the code ran:

  * one-way reachability between two routers with NO LINK, via
    longest-prefix fallback through a third router;
  * a border network reaching ITSELF, by a hairpin through a neighbour.

Both vanish when the priority is inverted, which is what makes the matrix an
LPM guard in its own right (§3). Pure Python, no inputs, no backend: fast tier.
The walk's agreement with airtel's homing-derived matrix needs the generated
`reachable.json`, so it is in `test_deltanet_fib_walk.py`, integration tier.
"""

import os
import shutil
import tempfile
import unittest

from bench.deltanet.fib_walk import LOOP, reachability, reached_pairs, regions
from bench.deltanet.policy import directed_pairs, emit_walked_policy
from bench.deltanet.preparation import build_model
from bench.deltanet.routers import (
    derive_router_topology, parse_router, router_homes, router_rule)
from bench.deltanet.topology import TopologyError
from bench.deltanet.trace import FIELD4_UNREAD, TraceError, parse_trace
from util.raw_data import RawDataError, verify_raw


#: Routers 1-4, every pair linked except 3-4.
#:
#:   10.0.0.0/8   homed at 1 -- 2, 3, 4 forward it to 1
#:   10.1.0.0/16  homed at 4 -- 1, 2 forward it to 4; 3 has no link to 4
#:   20.0.0.0/8   homed at 3 -- 1, 2 forward it to 3; 4 has no link to 3
#:   30.0.0.0/8   homed at 2 -- 1, 3, 4 forward it to 2
#:
#: So from 3, an address in 10.1/16 falls back to 10/8 and goes to 1, which
#: carries 10.1/16 and sends it to 4: 3 reaches 4 without a link. From 4, 20/8
#: has no rule and no container: 4 does NOT reach 3. And from 4, 10.1/16 --
#: its own -- falls back to 10/8, goes to 1, and comes back: 4 reaches 4.
#: The fourth field is 7 throughout, which D1 would refuse for every row.
_TRACE = [
    '+10.0.0.0/8,2,1,7', '+10.0.0.0/8,3,1,7', '+10.0.0.0/8,4,1,7',
    '+10.1.0.0/16,1,4,7', '+10.1.0.0/16,2,4,7',
    '+20.0.0.0/8,1,3,7', '+20.0.0.0/8,2,3,7',
    '+30.0.0.0/8,1,2,7', '+30.0.0.0/8,3,2,7', '+30.0.0.0/8,4,2,7',
]

_REACHED = {
    ('s2', 's1'), ('s3', 's1'), ('s4', 's1'),
    ('s1', 's4'), ('s2', 's4'), ('s3', 's4'), ('s4', 's4'),
    ('s1', 's3'), ('s2', 's3'),
    ('s1', 's2'), ('s3', 's2'), ('s4', 's2'),
}


def _model():
    inserts = parse_trace(_TRACE, field4=FIELD4_UNREAD)
    topology = derive_router_topology(inserts)
    homed = router_homes(inserts)
    return topology, homed, build_model(inserts, topology, homed,
                                        rule_of=router_rule)


class TestReadingWithoutD1(unittest.TestCase):

    def test_the_default_still_refuses_a_non_d1_field(self):
        with self.assertRaises(TraceError):
            parse_trace(_TRACE[:1])

    def test_unread_means_not_read(self):
        inserts = parse_trace(_TRACE[:1], field4=FIELD4_UNREAD)
        self.assertIsNone(inserts[0].priority)

    def test_an_unknown_reading_is_refused(self):
        self.assertRaises(ValueError, parse_trace, _TRACE, field4='guess')


class TestRouterTopology(unittest.TestCase):

    def test_ports_rename_the_adjacency(self):
        topology, _, _ = _model()
        self.assertEqual(topology.switches, [1, 2, 3, 4])
        self.assertEqual(len(topology.links), 5)
        self.assertNotIn(frozenset((3, 4)), topology.links)
        # port 1 is the border network, then neighbours in ascending order
        self.assertEqual(topology.ports[3], {1, 2, 3})
        self.assertEqual(topology.port_of[(3, 1)], 2)
        self.assertEqual(topology.port_of[(3, 2)], 3)
        self.assertEqual(topology.port_of[(1, 4)], 4)

    def test_a_port_name_is_refused(self):
        self.assertRaises(TopologyError, parse_router, 's1-2')

    def test_a_one_way_pair_is_refused(self):
        inserts = parse_trace(['+10.0.0.0/8,2,1,7'], field4=FIELD4_UNREAD)
        with self.assertRaises(TopologyError) as caught:
            derive_router_topology(inserts)
        self.assertIn('one direction', str(caught.exception))

    def test_forwarding_to_itself_is_refused(self):
        inserts = parse_trace(['+10.0.0.0/8,2,2,7'], field4=FIELD4_UNREAD)
        self.assertRaises(TopologyError, derive_router_topology, inserts)

    def test_homes_need_no_ports(self):
        _, homed, _ = _model()
        self.assertEqual(homed, {'10.0.0.0/8': 1, '10.1.0.0/16': 4,
                                 '20.0.0.0/8': 3, '30.0.0.0/8': 2})


class TestRouterModel(unittest.TestCase):

    def test_transit_rules_match_any_port_and_delivery_only_inter_ports(self):
        topology, homed, model = _model()
        at_one = [r for r in model['routes'] if r[0] == 'sw.s1']
        transit = [r for r in at_one if r[4] != ['fd=sw.s1.151']]
        delivery = [r for r in at_one if r[4] == ['fd=sw.s1.151']]
        self.assertTrue(transit and all(r[5] == [] for r in transit))
        self.assertEqual([r[3] for r in delivery], [['ipv4_dst=10.0.0.0/8']])
        self.assertEqual(sorted(delivery[0][5]),
                         ['sw.s1.102', 'sw.s1.103', 'sw.s1.104'])
        self.assertEqual(model['census']['delivery_rules'], len(homed))
        self.assertEqual(model['census']['transit_rules'], len(_TRACE))


class TestFibWalk(unittest.TestCase):

    def test_regions_skip_a_fully_covered_prefix(self):
        chains = regions(['10.0.0.0/8', '10.0.0.0/9', '10.128.0.0/9',
                          '10.1.0.0/16'])
        self.assertEqual(sorted(tuple(c) for c in chains), [
            ('10.0.0.0/9', '10.0.0.0/8'),
            ('10.1.0.0/16', '10.0.0.0/9', '10.0.0.0/8'),
            ('10.128.0.0/9', '10.0.0.0/8'),
        ])

    def test_the_hand_worked_matrix(self):
        _, _, model = _model()
        walked = reachability(model)
        self.assertEqual(reached_pairs(walked), _REACHED)
        self.assertFalse([k for k in walked if k[1] == LOOP])

    def test_inverting_lpm_changes_the_matrix(self):
        """ Shortest-first, 10/8 wins wherever both match, so NOTHING reaches
        4 -- 10.1/16's only home -- and 1 gains a hairpin: its packet for
        10.1/16 goes to 4 (1 carries no 10/8 rule on its border port), and 4
        sends it back under 10/8. This set was first written as only the two
        fallback cells, which was an incomplete hand derivation, not the walk
        being wrong; each of the five was then re-derived by hand. """
        _, _, model = _model()
        lpm = reached_pairs(reachability(model))
        inverted = reached_pairs(reachability(model, resolve='shortest'))
        self.assertEqual(lpm - inverted, {('s1', 's4'), ('s2', 's4'),
                                          ('s3', 's4'), ('s4', 's4')})
        self.assertEqual(inverted - lpm, {('s1', 's1')})

    def test_the_policy_states_the_walked_matrix(self):
        topology, _, model = _model()
        policy = emit_walked_policy(topology, reached_pairs(reachability(model)))
        self.assertIn('    s3 ---> s4\n', policy)
        self.assertIn('    s4 <--> s4\n', policy)
        self.assertEqual(directed_pairs(policy), _REACHED)


class TestDerivedManifest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='manifest_test_')
        with open(os.path.join(self.tmp, 'x.csv'), 'w') as handle:
            handle.write('x\n')
        digest = '5ab2d0e3f3eae5f5a3ceef4a9c0c1ab82ef6ce06f0b53e4c8c6b0d2f6e4a3d8b'
        with open(os.path.join(self.tmp, 'DERIVED.SHA256SUMS'), 'w') as handle:
            handle.write('%s  x.csv\n' % digest)
        with open(os.path.join(self.tmp, 'SHA256SUMS'), 'w') as handle:
            handle.write('')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_named_manifest_is_the_one_checked(self):
        verify_raw(self.tmp)                    # empty default manifest: fine
        with self.assertRaises(RawDataError) as caught:
            verify_raw(self.tmp, 'DERIVED.SHA256SUMS')
        self.assertIn('DERIVED.SHA256SUMS', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
