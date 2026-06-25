#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" Behavioral / invariant tests for the device models that previously had no
direct coverage: the application-layer gateway, the snapshot (stateful) packet
filter, and the generator/probe endpoints.
"""

import unittest

from rule.rule_model import Match, RuleField
from devices.packet_filter import PacketFilterModel
from devices.snapshot_packet_filter import (
    SnapshotPacketFilterModel, _swap_field, _reverse_quintuple
)
from devices.application_layer_gateway import ApplicationLayerGatewayModel
from devices.generator import GeneratorModel
from devices.probe import ProbeModel
from devices.abstract_firewall import (
    _BASE_ROUTING_EXACT, _BASE_ROUTING_WRONG_IO, _BASE_ROUTING_RULE
)
from rule.rule_model import Rule, Forward


def _wiring_endpoints_missing_from_ports(model):
    """ Returns wiring endpoints that are not declared ports of the model. """
    endpoints = set()
    for src, dst in model.wiring:
        endpoints.add(src)
        endpoints.add(dst)
    return sorted(e for e in endpoints if e not in model.ports)


class TestWiringInvariant(unittest.TestCase):
    """ Every internal wiring endpoint must be a declared port of the model.

    Regression guard for the application-layer gateway, which wired
    ``<node>.relays_out`` (a port that does not exist; the real port is
    ``<node>.relay_out``) -- a typo that silently broke ALG connectivity.
    """

    def test_packet_filter_wiring_consistent(self):
        model = PacketFilterModel('pf', ports=[1, 2])
        self.assertEqual(_wiring_endpoints_missing_from_ports(model), [])

    def test_snapshot_packet_filter_wiring_consistent(self):
        model = SnapshotPacketFilterModel('spf', ports=[1, 2])
        self.assertEqual(_wiring_endpoints_missing_from_ports(model), [])

    def test_application_layer_gateway_wiring_consistent(self):
        model = ApplicationLayerGatewayModel('alg', ports=[1, 2])
        self.assertEqual(_wiring_endpoints_missing_from_ports(model), [])

    def test_alg_relay_egress_is_wired(self):
        """ The relay's egress (relay_out) must be wired to the output filter. """
        model = ApplicationLayerGatewayModel('alg', ports=[1, 2])
        self.assertIn(
            ('alg.relay_out', 'alg.output_filter_in'), model.wiring
        )


class TestApplicationLayerGateway(unittest.TestCase):
    """ Tests the ALG model serialization. """

    def test_to_from_json_roundtrip(self):
        model = ApplicationLayerGatewayModel('alg', ports=[1, 2])
        self.assertEqual(
            ApplicationLayerGatewayModel.from_json(model.to_json()).to_json(),
            model.to_json()
        )


class TestGeneratorModel(unittest.TestCase):
    """ Tests the flow-generator endpoint model (previously untested). """

    def test_to_from_json_roundtrip(self):
        model = GeneratorModel(
            'gen', {'ipv6_src': [RuleField('ipv6_src', '2001:db8::1')]}
        )
        # The constructor maps OXM field names to internal names.
        self.assertIn('packet.ipv6.source', model.fields)
        self.assertEqual(
            GeneratorModel.from_json(model.to_json()).to_json(), model.to_json()
        )

    def test_empty_fields(self):
        model = GeneratorModel('gen')
        self.assertEqual(model.fields, {})
        self.assertEqual(model.to_json()['fields'], {})


class TestProbeModel(unittest.TestCase):
    """ Tests the probe endpoint model (previously untested). """

    def test_to_from_json_roundtrip_with_match(self):
        model = ProbeModel(
            'probe', 'universal',
            match=Match([RuleField('packet.ipv6.destination', '2001:db8::1')])
        )
        self.assertEqual(
            ProbeModel.from_json(model.to_json()).to_json(), model.to_json()
        )

    def test_to_from_json_roundtrip_with_path(self):
        model = ProbeModel('probe', 'existential', test_path=['.*(table=probe)'])
        self.assertEqual(
            ProbeModel.from_json(model.to_json()).to_json(), model.to_json()
        )


class TestFirewallAddRules(unittest.TestCase):
    """ Tests the firewall routing-rule priority-band expansion.

    AbstractFirewallModel.add_rules splits each routing rule into three
    priority bands (exact / wrong-io / normal) by offsetting rule.idx with the
    _BASE_ROUTING_* bases, all under the '<node>.routing' table.
    """

    def test_routing_rule_expands_into_three_bands(self):
        firewall = PacketFilterModel('fw', ports=['1', '2'])
        rule = Rule(
            'fw', 'fw.routing', 0,
            in_ports=['fw.1'],
            match=Match([RuleField('packet.ipv6.destination', '2001:db8::1')]),
            actions=[Forward(ports=['1'])],
        )

        firewall.add_rules([rule])

        banded = firewall._adds.get('fw.routing', [])
        self.assertEqual(len(banded), 3)
        # The three copies sit at the three band bases (rule idx was 0).
        self.assertEqual(
            sorted(r.idx for r in banded),
            sorted([_BASE_ROUTING_EXACT, _BASE_ROUTING_WRONG_IO, _BASE_ROUTING_RULE])
        )
        # All land in the routing table.
        self.assertTrue(all(r.tid == 'fw.routing' for r in banded))


class TestSnapshotHelpers(unittest.TestCase):
    """ Tests the stateful reverse-flow field swapping used by add_state. """

    def test_swap_source_destination(self):
        self.assertEqual(
            _swap_field(RuleField('packet.ipv6.source', 'v')),
            ('packet.ipv6.destination', 'v')
        )
        self.assertEqual(
            _swap_field(RuleField('packet.ipv6.destination', 'v')),
            ('packet.ipv6.source', 'v')
        )

    def test_swap_sport_dport(self):
        self.assertEqual(
            _swap_field(RuleField('packet.upper.sport', 'v')),
            ('packet.upper.dport', 'v')
        )
        self.assertEqual(
            _swap_field(RuleField('packet.upper.dport', 'v')),
            ('packet.upper.sport', 'v')
        )

    def test_swap_unrelated_field_unchanged(self):
        """ A field that is neither an address nor a port is left as-is. """
        self.assertEqual(
            _swap_field(RuleField('packet.ipv6.proto', '00000110')),
            ('packet.ipv6.proto', '00000110')
        )

    def test_reverse_quintuple_swaps_all_directional_fields(self):
        quintuple = Match([
            RuleField('packet.ipv6.source', 's'),
            RuleField('packet.ipv6.destination', 'd'),
            RuleField('packet.upper.sport', 'sp'),
            RuleField('packet.upper.dport', 'dp'),
            RuleField('packet.ipv6.proto', 'p'),
        ])
        reversed_ = _reverse_quintuple(quintuple)
        as_pairs = [(f.name, f.value) for f in reversed_]
        self.assertEqual(as_pairs, [
            ('packet.ipv6.destination', 's'),
            ('packet.ipv6.source', 'd'),
            ('packet.upper.dport', 'sp'),
            ('packet.upper.sport', 'dp'),
            ('packet.ipv6.proto', 'p'),
        ])


if __name__ == '__main__':
    unittest.main()
