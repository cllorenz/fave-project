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

""" wl_deltanet's model and its FPL (CLOUD_BENCH_PLAN.md §2.5).

`cloud_preparation` needs its port structure pinned because that structure is
INVENTED -- the NoD transfer function has no interfaces, so a mis-wiring yields
a model that builds cleanly and answers a different question. Here the ports
are read off the data, so these tests are a different kind: they check that the
model says what the trace says, and they pin the ONE thing that is invented --
the 1,400 synthesised delivery rules, without which no probe could ever fire.

The mutation evidence is not here, because it needs a live backend: claiming
`s1 ---> s8`, a cell the data plane cannot satisfy, yields exactly one
violation naming it. §2.5 records that run.
"""

import collections
import os
import unittest

from bench.wl_deltanet.deltanet_policy import (
    directed_pairs,
    emit_inventory,
    emit_policy,
    homing_switches,
    role_endpoints,
    role_name,
)
from bench.wl_deltanet.deltanet_preparation import (
    build_model,
    device_name,
    endpoint_name,
    in_port,
    out_port,
)
from bench.wl_deltanet.deltanet_topology import (
    EXTERNAL_PORT, derive_topology, homes, parse_node)
from bench.wl_deltanet.deltanet_trace import RAW, TRACES, read_trace


def _load(which=0):
    inserts = read_trace(os.path.join(RAW, TRACES[which]))
    return inserts, derive_topology(inserts), homes(inserts)


class TestDeltanetModel(unittest.TestCase):
    """ The model says what the trace says. """

    @classmethod
    def setUpClass(cls):
        cls.inserts, cls.topology, cls.homed = _load()
        cls.model = build_model(cls.inserts, cls.topology, cls.homed)

    def test_one_device_per_switch_with_two_fave_ports_per_trace_port(self):
        devices = self.model['topology']['devices']
        self.assertEqual(len(devices), len(self.topology.switches))
        for name, kind, ports, tables in devices:
            self.assertEqual(kind, 'switch')
            self.assertIn(name, tables)
            switch = int(name.split('.s')[1])
            self.assertEqual(len(ports), 2 * len(self.topology.ports[switch]))

    def test_every_link_joins_an_out_port_to_the_matching_in_port(self):
        """ The wiring is derived, so it can be checked against the topology. """
        links = self.model['topology']['links']
        self.assertEqual(len(links), 2 * len(self.topology.links))
        for src, dst, bulk in links:
            self.assertFalse(bulk)
            src_dev, src_port = src.rsplit('.', 1)
            dst_dev, dst_port = dst.rsplit('.', 1)
            left = int(src_dev.split('.s')[1])
            right = int(dst_dev.split('.s')[1])
            self.assertEqual(
                int(src_port), out_port(left, self.topology.egress_port(left, right)))
            self.assertEqual(
                int(dst_port), in_port(right, self.topology.egress_port(right, left)))

    def test_every_trace_rule_becomes_one_route(self):
        census = self.model['census']
        self.assertEqual(census['transit_rules'], len(self.inserts))
        self.assertEqual(
            census['rules'], census['transit_rules'] + census['delivery_rules'])
        self.assertEqual(len(self.model['routes']), census['rules'])

    def test_one_synthesised_delivery_rule_per_prefix(self):
        """ The single invention, counted separately so it can be audited. """
        self.assertEqual(self.model['census']['delivery_rules'], len(self.homed))

    def test_the_delivery_rules_shadow_nothing(self):
        """ Measured, not assumed: no prefix has a rule at its own home. """
        for insert in self.inserts:
            switch, _port = parse_node(insert.router)
            self.assertNotEqual(self.homed[insert.prefix], switch)

    def test_a_delivery_rule_never_takes_the_external_in_port(self):
        """ Which is what stops a packet hairpinning back to its own border. """
        for device, _table, _idx, _match, actions, in_ports in self.model['routes']:
            switch = int(device.split('.s')[1])
            if actions != ['fd=%s.%d' % (device, out_port(switch, EXTERNAL_PORT))]:
                continue
            self.assertNotIn(
                '%s.%d' % (device, in_port(switch, EXTERNAL_PORT)), in_ports)

    def test_rules_are_ordered_longest_prefix_first(self):
        """ NetPlumber resolves priority by rule index, so order IS the FIB. """
        by_device = collections.defaultdict(list)
        for device, _table, index, match, _actions, _in_ports in self.model['routes']:
            length = int(match[0].split('/')[1])
            by_device[device].append((index, length))
        for device, entries in by_device.items():
            lengths = [length for _index, length in sorted(entries)]
            self.assertEqual(lengths, sorted(lengths, reverse=True), device)

    def test_a_generator_and_a_probe_on_every_external_port(self):
        sources = self.model['sources']
        probes = self.model['probes']
        self.assertEqual(len(sources['devices']), len(self.topology.switches))
        self.assertEqual(len(probes['devices']), len(self.topology.switches))
        for switch in self.topology.switches:
            self.assertIn(
                ['source.%s.1' % endpoint_name(switch),
                 '%s.%d' % (device_name(switch), in_port(switch, EXTERNAL_PORT)),
                 True],
                [list(link) for link in sources['links']])
            self.assertIn(
                ['%s.%d' % (device_name(switch), out_port(switch, EXTERNAL_PORT)),
                 'probe.%s.1' % endpoint_name(switch), False],
                [list(link) for link in probes['links']])

    def test_both_traces_build_a_model_of_the_same_shape(self):
        other_inserts, other_topology, other_homed = _load(1)
        other = build_model(other_inserts, other_topology, other_homed)
        for key in ('devices', 'links', 'rules', 'sources', 'probes'):
            self.assertEqual(self.model['census'][key], other['census'][key], key)


class TestDeltanetPolicy(unittest.TestCase):
    """ The matrix is OURS, and it is two-sided. """

    @classmethod
    def setUpClass(cls):
        cls.inserts, cls.topology, cls.homed = _load()
        cls.inventory = emit_inventory(cls.topology, cls.homed)
        cls.policy = emit_policy(cls.topology, cls.homed)

    def test_one_role_per_switch_and_one_endpoint_per_role(self):
        endpoints = role_endpoints(self.topology)
        self.assertEqual(len(endpoints), len(self.topology.switches))
        for switch in self.topology.switches:
            self.assertEqual(endpoints[role_name(switch)],
                             [endpoint_name(switch)])
            self.assertIn('def role %s\n' % role_name(switch), self.inventory)

    def test_the_inventory_declares_no_service(self):
        """ There are no transport fields anywhere in the data. """
        self.assertNotIn('def service', self.inventory)
        self.assertNotIn('offers', self.inventory)

    def test_the_inventory_declares_no_address(self):
        """ A homing switch stands for 100 prefixes; `ipv4` carries one.

        Asserted over the ATTRIBUTE lines rather than the file, because the
        header explains at length why the attribute is absent and an
        `assertNotIn` over the whole text matches that explanation.
        """
        attributes = [
            line.strip() for line in self.inventory.splitlines()
            if line.startswith('    ')]
        self.assertTrue(attributes)
        for attribute in attributes:
            self.assertFalse(attribute.startswith(('ipv4', 'ipv6')), attribute)

    def test_the_policy_permits_the_full_cross_product_minus_the_diagonal(self):
        """ Stated over the EXPANDED pairs, because the policy mixes operators.

        This is the assertion that lets `emit_policy` be concise: whatever mix
        of `<-->` and `--->` it writes, the permissions have to come to the same
        210 ordered pairs an all-unidirectional policy would state.
        """
        targets = homing_switches(self.homed)
        expected = {
            (role_name(source), role_name(target))
            for target in targets
            for source in self.topology.switches
            if source != target
        }
        self.assertEqual(directed_pairs(self.policy), expected)
        self.assertEqual(len(expected), 210)

    def _rules(self):
        """ The policy's rule lines, without its explanatory header.

        Every assertion about operators goes through this. Twice now a plain
        `assertNotIn` over the whole file has matched the comment explaining
        why an operator is NOT used, which is a test that fails on its own
        documentation.
        """
        return [line.strip() for line in self.policy.splitlines()
                if line.startswith('    ')]

    def test_symmetric_pairs_are_bidirectional_and_the_rest_are_not(self):
        """ The mix is the s8/s9 finding made visible in the policy itself. """
        rules = self._rules()
        targets = homing_switches(self.homed)
        senders = [s for s in self.topology.switches if s not in targets]

        self.assertEqual(sum('<-->' in rule for rule in rules),
                         len(targets) * (len(targets) - 1) // 2)
        self.assertEqual(sum('--->' in rule for rule in rules),
                         len(senders) * len(targets))
        self.assertEqual(len(rules), 119)

        # A switch that homes nothing may never appear on the right of a rule.
        for switch in senders:
            for rule in rules:
                self.assertFalse(rule.endswith(' %s' % role_name(switch)), rule)

    def test_no_rule_is_stateful(self):
        """ `<->>` would condition the return on RELATED,ESTABLISHED, which is
        a claim about conntrack in a plane that matches only a prefix.

        Over the RULE lines, not the file: the header explains why the operator
        is unused, and an `assertNotIn` over the whole text matches that.
        """
        for rule in self._rules():
            self.assertNotIn('<->>', rule)

    def test_no_rule_names_a_role_as_its_own_peer(self):
        for switch in self.topology.switches:
            name = role_name(switch)
            for operator in ('--->', '<-->'):
                self.assertNotIn(
                    '    %s %s %s\n' % (name, operator, name), self.policy)
        self.assertFalse(
            [pair for pair in directed_pairs(self.policy) if pair[0] == pair[1]])

    def test_two_switches_are_sources_but_never_destinations(self):
        """ s8 and s9 home nothing, which is what makes 30 cells DENY. """
        targets = set(homing_switches(self.homed))
        self.assertEqual(sorted(set(self.topology.switches) - targets), [8, 9])

    def test_both_traces_state_the_same_matrix(self):
        other_inserts, other_topology, other_homed = _load(1)
        self.assertEqual(emit_policy(other_topology, other_homed), self.policy)
        self.assertEqual(emit_inventory(other_topology, other_homed),
                         self.inventory)


if __name__ == '__main__':
    unittest.main()
