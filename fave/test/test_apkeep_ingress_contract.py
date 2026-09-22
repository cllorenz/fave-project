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

""" The APKeep adapter refuses what it cannot carry (CLOUD_BENCH_PLAN.md §2.7).

APKeep's `ForwardElement` is a destination-prefix trie keyed by DEVICE:
`Checker.traverseFowardingGraph` uses the arrival port only to look the element
up and then discards it. So a rule restricted to some ingress ports applies at
all of them -- an over-approximation, which is the direction that reads as a
result rather than as a failure.

These are pure logic and need no JVM: the contract is a property of the
captured model, so it is asserted where it can be asserted cheaply. The
end-to-end evidence is separate -- wl_deltanet refuses, wl_stanford/wl_i2/
wl_ifi/wl_cloud stay green -- and lives in the integration tier and §2.7.
"""

import logging
import unittest

from apkeep.adapter import (
    ACCOUNT_APPROXIMATE,
    ACCOUNT_COMPLETE,
    APKeepAdapter,
    UntranslatedSemantics,
)


def _adapter(rows, devices, edges, accounted=None):
    adapter = APKeepAdapter(logging.getLogger('test_apkeep_contract'))
    adapter._fwd_table = rows
    adapter._fwd_devices = set(devices)
    if accounted:
        adapter._ingress_accounted = dict(accounted)
    return adapter, edges


def _row(idx, in_ports):
    return {'idx': idx, 'ports': ['1'], 'in_ports': list(in_ports),
            'match': {}, 'rw': {}}


class TestIngressContract(unittest.TestCase):
    """ Three outcomes: silence, a declared account, or a refusal. """

    def test_a_rule_applying_at_every_ingress_port_qualifies_nothing(self):
        adapter, edges = _adapter(
            {'d': [_row(1, ['1', '2'])]}, ['d'],
            ['x 9 d 1', 'y 9 d 2'])
        self.assertEqual(adapter._ingress_qualified(edges), {})
        adapter._assert_ingress_accounted(edges)          # must not raise

    def test_a_rule_listing_no_in_port_qualifies_nothing(self):
        """ An unqualified rule applies everywhere, which is what a trie does. """
        adapter, edges = _adapter(
            {'d': [_row(1, [])]}, ['d'], ['x 9 d 1', 'y 9 d 2'])
        self.assertEqual(adapter._ingress_qualified(edges), {})

    def test_a_rule_keyed_to_an_INTERNAL_pipeline_port_qualifies_nothing(self):
        """ The first form of this check got this wrong and flagged every
        router in the tree. FaVe's router keys its routing table to
        `r.routing_in`, which is not a topology ingress port at all; the
        pipeline is modelled as separate elements. """
        adapter, edges = _adapter(
            {'r': [_row(0, ['routing_in'])]}, ['r'], ['source.A 1 r 1'])
        self.assertEqual(adapter._ingress_qualified(edges), {})
        adapter._assert_ingress_accounted(edges)          # must not raise

    def test_a_rule_naming_every_ingress_port_qualifies_nothing(self):
        adapter, edges = _adapter(
            {'d': [_row(1, ['1', '2'])]}, ['d'], ['x 9 d 1'])
        self.assertEqual(adapter._ingress_qualified(edges), {})

    def test_a_restricted_rule_with_no_account_is_REFUSED(self):
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1', 'y 9 d 2'])
        self.assertEqual(adapter._ingress_qualified(edges), {'d': [1]})
        with self.assertRaises(UntranslatedSemantics) as caught:
            adapter._assert_ingress_accounted(edges)
        message = str(caught.exception)
        self.assertIn('in-port-qualified forwarding', message)
        self.assertIn('over-approximation', message)
        self.assertIn('d', message)

    def test_a_declared_account_is_accepted(self):
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1', 'y 9 d 2'],
            accounted={'d': (ACCOUNT_COMPLETE, 'a mechanism')})
        adapter._assert_ingress_accounted(edges)          # must not raise

    def test_an_approximate_account_is_accepted_but_WARNED(self):
        """ The approximation has to travel with the result, not be rediscovered. """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1', 'y 9 d 2'],
            accounted={'d': (ACCOUNT_APPROXIMATE, 'a partial mechanism')})
        with self.assertLogs(adapter.logger, level='WARNING') as captured:
            adapter._assert_ingress_accounted(edges)
        self.assertIn('APPROXIMATELY', ' '.join(captured.output))

    def test_a_device_not_realised_as_a_ForwardElement_is_not_checked(self):
        """ A first-match table or a collapsed stage is somebody else's problem. """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, [], ['x 9 d 1', 'y 9 d 2'])
        self.assertEqual(adapter._ingress_qualified(edges), {})

    def test_a_packet_filter_device_is_not_checked_here(self):
        """ It becomes a FilterElement pipeline, and `_build_pf_pipeline`
        subtracts it AFTER this check runs -- so the exclusion has to be
        explicit. Not a claim that the pipeline carries ingress qualification:
        wl_up's dmz/wifi default route is in-port-qualified and that is an open
        question (§2.7). """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1', 'y 9 d 2'])
        adapter._filter_devices = {'d'}
        self.assertEqual(adapter._ingress_qualified(edges), {})
        adapter._assert_ingress_accounted(edges)          # must not raise

    def test_ingress_is_read_from_the_FINAL_wiring(self):
        """ The collapses and gates rewrite the topology before this runs, so a
        port whose edge was removed is no longer an ingress and no longer
        qualifies a rule that omits it. """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1'])
        self.assertEqual(adapter._ingress_qualified(edges), {})


if __name__ == '__main__':
    unittest.main()
