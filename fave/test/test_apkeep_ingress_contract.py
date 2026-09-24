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

    def test_a_table_realised_as_NEITHER_element_is_not_checked(self):
        """ A collapsed stage is somebody else's problem.

        Not a first-match table, though -- that used to fall in here too and no
        longer does; see the next two tests.
        """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, [], ['x 9 d 1', 'y 9 d 2'])
        self.assertEqual(adapter._ingress_qualified(edges), {})

    def test_a_FIRST_MATCH_device_IS_checked(self):
        """ `_build` moves a table that is not a dst-prefix trie onto a
        `FilterElement` and removes it from `_fwd_devices` BEFORE the demux and
        this refusal run. Keying the check on `_fwd_devices` alone therefore made
        such a device invisible to it -- and a `FilterElement` carries an arrival
        port no better than a `ForwardElement` does.

        Latent when it was closed (no shipped workload is both first-match and
        discriminating), and load-bearing for any staged table realised this way.
        """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, [], ['x 9 d 1', 'y 9 d 2'])
        adapter._fm_devices = {'d'}
        self.assertEqual(adapter._ingress_qualified(edges), {'d': [1]})
        self.assertRaises(UntranslatedSemantics,
                          adapter._assert_ingress_accounted, edges)

    def test_a_FIRST_MATCH_device_with_a_declared_account_is_accepted(self):
        """ The refusal is about an UNDECLARED approximation, not about the
        element type: declare a mechanism and the device passes, exactly as a
        ForwardElement device does. """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, [], ['x 9 d 1', 'y 9 d 2'],
            accounted={'d': (ACCOUNT_COMPLETE, 'a test')})
        adapter._fm_devices = {'d'}
        adapter._assert_ingress_accounted(edges)          # must not raise

    def test_a_packet_filter_device_IS_checked(self):
        """ It used to be excluded wholesale, which was a scope statement rather
        than a claim (§2.7). Now it is a checked claim.

        `_build_pf_pipeline` does carry ingress qualification -- an `in_port`
        MATCH becomes a per-port prefilter element -- but that is a different
        field from `rule.in_ports`, which is what this measures, so neither
        subsumes the other and a device discriminating by the latter is refused.
        """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1', 'y 9 d 2'])
        adapter._filter_devices = {'d'}
        self.assertEqual(adapter._ingress_qualified(edges), {'d': [1]})
        self.assertRaises(UntranslatedSemantics,
                          adapter._assert_ingress_accounted, edges)

    def test_ingress_is_read_from_the_FINAL_wiring(self):
        """ The collapses and gates rewrite the topology before this runs, so a
        port whose edge was removed is no longer an ingress and no longer
        qualifies a rule that omits it. """
        adapter, edges = _adapter(
            {'d': [_row(1, ['1'])]}, ['d'], ['x 9 d 1'])
        self.assertEqual(adapter._ingress_qualified(edges), {})


class TestIngressDemux(unittest.TestCase):
    """ Phase (b): the split, and that it carries BOTH forwarding stores.

    A device's forwarding can live in `_fwd_rules` (a `ForwardElement`) or in
    `_router_fib` (a dst-LPM `FilterElement`, for an IPv6 router), and neither
    element type carries an ingress port. A split that re-keyed only one of
    them would drop the other's routes -- which is exactly what happened on
    wl_up before this: its dmz/wifi IPv6 host routes stayed filed under a name
    that no longer existed as an element, and the run reported violations
    NetPlumber and ad6 do not.
    """

    def _adapter_with(self, fwd_rows, fwd_rules, fib, ipv6):
        adapter = APKeepAdapter(logging.getLogger('test_apkeep_demux'))
        adapter._fwd_table = fwd_rows
        adapter._fwd_devices = set(fwd_rows)
        adapter._fwd_rules = list(fwd_rules)
        adapter._router_fib = dict(fib)
        adapter._ipv6_fib_devices = set(ipv6)
        return adapter

    def test_a_discriminating_device_is_split_per_ingress_class(self):
        rule_a = '+ fwd d 0 0 9 0'
        adapter = self._adapter_with(
            {'d': [_row(1, ['1'])]}, [rule_a], {}, set())
        adapter._fwd_ingress = {rule_a: {'1'}}
        edges = ['x 9 d 1', 'y 9 d 2', 'd 9 z 1']
        new_edges, new_rules = adapter._demux_ingress(edges, [rule_a])

        sep = adapter.INGRESS_CLASS_SEP
        self.assertEqual(adapter._fwd_devices, {'d%s1' % sep, 'd%s2' % sep})
        # the rule follows its own class only
        self.assertEqual(new_rules, ['+ fwd d%s1 0 0 9 0' % sep])
        # arriving links land on the class owning the port; the egress is
        # duplicated across classes
        self.assertIn('x 9 d%s1 1' % sep, new_edges)
        self.assertIn('y 9 d%s2 2' % sep, new_edges)
        self.assertIn('d%s1 9 z 1' % sep, new_edges)
        self.assertIn('d%s2 9 z 1' % sep, new_edges)
        # and nothing still refers to the unsplit device
        adapter._assert_ingress_accounted(new_edges)

    def test_the_router_FIB_is_re_keyed_in_lockstep(self):
        """ The wl_up defect: split the element, lose the IPv6 routes. """
        rule = '+ fwd d 0 0 9 0'
        fib = {'d': [('2001:db8::1', '8', 128, None),      # holds everywhere
                     (None, '9', 0, frozenset({'1'}))]}    # holds at port 1
        adapter = self._adapter_with(
            {'d': [_row(1, ['1'])]}, [rule], fib, {'d'})
        adapter._fwd_ingress = {rule: {'1'}}
        edges = ['x 9 d 1', 'y 9 d 2', 'd 9 z 1']
        adapter._demux_ingress(edges, [rule])

        sep = adapter.INGRESS_CLASS_SEP
        self.assertNotIn('d', adapter._router_fib)
        self.assertNotIn('d', adapter._ipv6_fib_devices)
        self.assertEqual(set(adapter._router_fib), {'d%s1' % sep, 'd%s2' % sep})
        # the everywhere-entry reaches both classes, the qualified one only its own
        self.assertEqual(len(adapter._router_fib['d%s1' % sep]), 2)
        self.assertEqual(len(adapter._router_fib['d%s2' % sep]), 1)
        self.assertEqual(adapter._ipv6_fib_devices,
                         {'d%s1' % sep, 'd%s2' % sep})

    def test_a_packet_filter_is_NOT_split_by_the_demux(self):
        """ The demux re-keys `_fwd_rules` and `_router_fib`; a filter device
        also lives in `_pf_rules`/`_filter_fib`, which it does not touch. So it
        must leave one alone rather than drop its chain rules -- the §2.8 wl_up
        defect, one store further along. """
        rule = '+ fwd d 0 0 9 0'
        adapter = self._adapter_with({'d': [_row(1, ['1'])]}, [rule], {}, set())
        adapter._fwd_ingress = {rule: {'1'}}
        adapter._filter_devices = {'d'}
        edges = ['x 9 d 1', 'y 9 d 2', 'd 9 z 1']
        new_edges, new_rules = adapter._demux_ingress(edges, [rule])

        self.assertEqual(new_edges, edges)        # untouched
        self.assertEqual(new_rules, [rule])
        self.assertEqual(adapter._fwd_devices, {'d'})
        # and therefore still refused, which is the honest outcome
        self.assertRaises(UntranslatedSemantics,
                          adapter._assert_ingress_accounted, edges)

    def test_a_FIRST_MATCH_device_is_NOT_split_by_the_demux(self):
        """ Same shape as the packet_filter case, one store further along: a
        first-match device's rules live in `_fwd_table`, which
        `_build_first_match_tables` has already emitted by the time the demux
        runs and which the demux does not re-key. Splitting one would rename the
        element and leave its rules filed under the old name. """
        rule = '+ fwd d 0 0 9 0'
        adapter = self._adapter_with({'d': [_row(1, ['1'])]}, [rule], {}, set())
        adapter._fwd_ingress = {rule: {'1'}}
        adapter._fm_devices = {'d'}
        edges = ['x 9 d 1', 'y 9 d 2', 'd 9 z 1']
        new_edges, new_rules = adapter._demux_ingress(edges, [rule])

        self.assertEqual(new_edges, edges)        # untouched
        self.assertEqual(new_rules, [rule])
        self.assertRaises(UntranslatedSemantics,
                          adapter._assert_ingress_accounted, edges)

    def test_the_class_split_accounts_for_router_FIB_entries_too(self):
        """ A device with NO `+ fwd` rules can still discriminate, via the FIB. """
        fib = {'d': [('2001:db8::1', '8', 128, frozenset({'1'}))]}
        adapter = self._adapter_with({'d': [_row(1, ['1'])]}, [], fib, {'d'})
        edges = ['x 9 d 1', 'y 9 d 2', 'd 9 z 1']
        adapter._demux_ingress(edges, [])
        sep = adapter.INGRESS_CLASS_SEP
        self.assertEqual(set(adapter._router_fib), {'d%s1' % sep})
        self.assertEqual(adapter._fwd_devices, {'d%s1' % sep, 'd%s2' % sep})

    def test_the_separator_is_not_one_the_NDD_engine_reserves(self):
        """ `|` keys NddReachabilityEngine/AtomForwarding's per-hop cache and is
        recovered with indexOf('|'); an element named `d|1` corrupts it, which
        cost 210 silently-failed checks. """
        self.assertNotIn(APKeepAdapter.INGRESS_CLASS_SEP, '|.')


if __name__ == '__main__':
    unittest.main()
