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

""" Unit tests for netplumber.adapter -- both the pure bit-packing helpers and
the model->NetPlumber-RPC translation in NetPlumberAdapter.

The translation methods are tested backend-free by patching the module's
``jsonrpc`` so every RPC call is recorded instead of sent: the unit under test
is *what the adapter tells NetPlumber* (and its own bookkeeping), not the wire
protocol (covered separately in test_jsonrpc_client). A wrong translation
silently corrupts the verification model, so this is the highest-value gap.
"""

import logging
import unittest
from unittest import mock

from netplumber.adapter import (
    NetPlumberAdapter,
    _calc_port, _calc_rule_index, _expand_field,
    _TABLE_IDX_MAX, _RULE_IDX_MAX, _NEG_IDX_MAX,
)
from devices.abstract_device import AbstractDeviceModel
from devices.packet_filter import PacketFilterModel
from devices.switch import SwitchModel
from devices.generator import GeneratorModel
from devices.probe import ProbeModel
from rule.rule_model import Rule, Match, RuleField, Forward


class TestCalcRuleIndex(unittest.TestCase):
    """ Tests the (t_idx<<32)+(r_idx<<12)+n_idx rule-id packing. """

    def test_rule_index_only(self):
        self.assertEqual(_calc_rule_index(5), 5 << 12)

    def test_rule_index_full_packing(self):
        self.assertEqual(
            _calc_rule_index(5, t_idx=2, n_idx=3), (2 << 32) + (5 << 12) + 3
        )

    def test_negation_index_occupies_low_bits(self):
        """ The negation index lives in the low 12 bits, below the rule index. """
        self.assertEqual(_calc_rule_index(0, t_idx=0, n_idx=7), 7)

    def test_index_bounds_asserted(self):
        """ Each component is bounded; exceeding its width is a contract break. """
        with self.assertRaises(AssertionError):
            _calc_rule_index(_RULE_IDX_MAX + 1)
        with self.assertRaises(AssertionError):
            _calc_rule_index(0, t_idx=_TABLE_IDX_MAX + 1)
        with self.assertRaises(AssertionError):
            _calc_rule_index(0, n_idx=_NEG_IDX_MAX + 1)


class TestCalcPort(unittest.TestCase):
    """ Tests the (tab<<16)+port_index port packing. """

    def setUp(self):
        self.model = AbstractDeviceModel(
            'foo', tables={'foo.1': []},
            ports={'foo.1': 'foo.1', 'foo.2': 'foo.1'}
        )

    def test_port_packing(self):
        # port_index is the position in the sorted port list.
        self.assertEqual(_calc_port(1, self.model, 'foo.1'), (1 << 16) + 0)
        self.assertEqual(_calc_port(1, self.model, 'foo.2'), (1 << 16) + 1)
        self.assertEqual(_calc_port(3, self.model, 'foo.1'), (3 << 16) + 0)

    def test_missing_port_takes_fallback(self):
        """ A port that is not in the model falls back to (tab<<16)+1.

        Regression: port_index raises ValueError (via list.index), so the
        fallback's `except` must catch ValueError as well as KeyError -- it
        previously caught only KeyError, making the fallback unreachable.
        """
        self.assertEqual(_calc_port(1, self.model, 'does.not.exist'), (1 << 16) + 1)
        self.assertEqual(_calc_port(5, self.model, 'nope'), (5 << 16) + 1)


class TestExpandField(unittest.TestCase):
    """ Tests negated-field expansion into a set of complementary vectors. """

    def test_expand_flips_each_concrete_bit(self):
        """ Each concrete bit becomes its own vector with that bit inverted and
        all others wildcarded; wildcard bits contribute no vector. """
        vectors = [v.vector for v in _expand_field(RuleField('related', '00000110'))]
        self.assertEqual(vectors, [
            '1xxxxxxx',   # bit 0 was 0 -> 1
            'x1xxxxxx',   # bit 1 was 0 -> 1
            'xx1xxxxx',   # bit 2 was 0 -> 1
            'xxx1xxxx',   # bit 3 was 0 -> 1
            'xxxx1xxx',   # bit 4 was 0 -> 1
            'xxxxx0xx',   # bit 5 was 1 -> 0
            'xxxxxx0x',   # bit 6 was 1 -> 0
            'xxxxxxx1',   # bit 7 was 0 -> 1
        ])

    def test_all_wildcard_expands_to_nothing(self):
        """ A field with no concrete bits expands to the empty set. """
        self.assertEqual(_expand_field(RuleField('related', 'xxxxxxxx')), [])


class _AdapterTestBase(unittest.TestCase):
    """ Constructs an adapter with the module's jsonrpc patched out, so RPC
    calls are recorded rather than sent. No socket / backend involved. """

    def setUp(self):
        patcher = mock.patch('netplumber.adapter.jsonrpc')
        self.jsonrpc = patcher.start()
        self.addCleanup(patcher.stop)
        log = logging.getLogger('test_adapter')
        log.setLevel(logging.WARNING)   # keep the DEBUG/TRACE branches quiet
        self.adapter = NetPlumberAdapter(['SOCK'], log)


class TestAdapterAddTables(_AdapterTestBase):
    """ Tests model.tables -> jsonrpc.add_table translation + bookkeeping. """

    def test_packet_filter_tables_get_sequential_indices_and_packed_ports(self):
        model = PacketFilterModel('fw', ports=['1', '2'])
        self.adapter.add_tables(model)

        # one add_table per table; fresh indices 1..N.
        self.assertEqual(self.jsonrpc.add_table.call_count, len(model.tables))
        self.assertEqual(
            sorted(self.adapter.tables.values()),
            list(range(1, len(model.tables) + 1))
        )
        # every emitted port packs its table index in the high bits (idx<<16).
        for call in self.jsonrpc.add_table.call_args_list:
            socks, idx, ports = call.args
            self.assertEqual(socks, ['SOCK'])
            self.assertTrue(all((port >> 16) == idx for port in ports))
        # the port bookkeeping is consistent with what was emitted.
        for port, portno in self.adapter.ports.items():
            self.assertEqual(self.adapter.ports[port], portno)

    def test_switch_tables_use_table_ids(self):
        switch = SwitchModel('sw', ports=['1', '2'])
        self.adapter.add_tables(switch)
        self.assertEqual(self.jsonrpc.add_table.call_count, 1)
        self.assertIn('sw.1', self.adapter.tables)

    def test_existing_table_not_re_added(self):
        model = PacketFilterModel('fw', ports=['1', '2'])
        self.adapter.add_tables(model)
        first = self.jsonrpc.add_table.call_count
        self.adapter.add_tables(model)   # idempotent: tables already known
        self.assertEqual(self.jsonrpc.add_table.call_count, first)


class TestAdapterAddWiring(_AdapterTestBase):
    """ Tests model.wiring -> jsonrpc.add_link translation. """

    def setUp(self):
        super().setUp()
        self.model = PacketFilterModel('fw', ports=['1', '2'])
        self.adapter.add_tables(self.model)   # ports must be known first

    def test_wiring_emits_links_and_records_them(self):
        self.adapter.add_wiring(self.model)
        self.assertTrue(self.jsonrpc.add_link.called)
        # every link is recorded in self.links (global src -> [global dst]).
        self.assertTrue(self.adapter.links)
        for call in self.jsonrpc.add_link.call_args_list:
            _socks, gsrc, gdst = call.args
            self.assertIn(gdst, self.adapter.links[gsrc])

    def test_wiring_is_idempotent(self):
        self.adapter.add_wiring(self.model)
        count = self.jsonrpc.add_link.call_count
        self.adapter.add_wiring(self.model)   # existing wires are skipped
        self.assertEqual(self.jsonrpc.add_link.call_count, count)


class TestAdapterAddRules(_AdapterTestBase):
    """ Tests rule translation: rule-index packing + rule_ids bookkeeping. """

    def test_add_rules_packs_index_and_records_ids(self):
        switch = SwitchModel('sw', ports=['1', '2'])
        # The adapter consumes model.tables (the aggregator merges _adds first).
        switch.tables['sw.1'] = [Rule(
            'sw', 'sw.1', 0,
            in_ports=['sw.1'],
            match=Match([RuleField('packet.ipv6.destination', '2001:db8::1')]),
            actions=[Forward(['sw.2'])],
        )]
        self.jsonrpc.add_rules_batch.return_value = [101]

        self.adapter.add_tables(switch)
        self.adapter.add_rules(switch)

        self.assertEqual(self.jsonrpc.add_rules_batch.call_count, 1)
        # the np rule id is the packed (table<<32)+(rule<<12); table sw.1 -> idx 1.
        expected_key = _calc_rule_index(0, t_idx=self.adapter.tables['sw.1'])
        self.assertEqual(self.adapter.rule_ids[expected_key], [101])


class TestAdapterEndpoints(_AdapterTestBase):
    """ Tests generator/probe source-node translation. """

    def test_add_generator_emits_source_and_records_it(self):
        self.jsonrpc.add_source.return_value = 7001
        gen = GeneratorModel('gen', {'ipv6_src': [RuleField('ipv6_src', '2001:db8::1')]})
        self.adapter.add_generator(gen)

        self.assertEqual(self.jsonrpc.add_source.call_count, 1)
        idx, sid, model = self.adapter.generators['gen']
        self.assertEqual(sid, 7001)
        self.assertIs(model, gen)

    def test_add_generators_bulk(self):
        self.jsonrpc.add_sources_bulk.return_value = {1: 9001}
        gen = GeneratorModel('gen', {'ipv6_src': [RuleField('ipv6_src', '2001:db8::1')]})
        self.adapter.add_generators_bulk([gen])
        self.assertEqual(self.jsonrpc.add_sources_bulk.call_count, 1)
        self.assertEqual(self.adapter.generators['gen'][1], 9001)

    def test_add_probe_emits_source_probe_and_records_it(self):
        self.jsonrpc.add_source_probe.return_value = 8001
        # A probe must carry a test expression; a header-space test_fields needs
        # no table lookup (unlike a path that references a table).
        probe = ProbeModel(
            'probe', 'universal',
            match=Match([RuleField('packet.ipv6.destination', '2001:db8::1')]),
            test_fields={'ipv6_dst': [RuleField('ipv6_dst', '2001:db8::1')]},
        )
        self.adapter.add_probe(probe)
        self.assertEqual(self.jsonrpc.add_source_probe.call_count, 1)
        self.assertIn('probe', self.adapter.probes)


class TestGetIndexForSrc(_AdapterTestBase):
    """ Pins _get_index_for_src's generator-name extraction.

    NOTE: it uses ``src.rstrip('1').rstrip('.')`` -- a *character-set* strip, not
    a suffix strip. It resolves the common '<gen>.1' port correctly, and returns
    the not-found sentinel index (-1) for an unknown source. The character-set
    behavior is fragile for non-'.1' ports (flagged in the strategy); this pins
    the current contract.
    """

    def test_resolves_known_generator_via_dot_one_port(self):
        self.jsonrpc.add_source.return_value = 5001
        self.adapter.add_generator(GeneratorModel('gen', {'ipv6_src': [RuleField('ipv6_src', '2001:db8::1')]}))
        gen_idx = self.adapter.generators['gen'][0]
        self.assertEqual(self.adapter._get_index_for_src('gen.1'), gen_idx)

    def test_unknown_source_returns_sentinel(self):
        self.assertEqual(self.adapter._get_index_for_src('nope.1'), -1)


if __name__ == '__main__':
    unittest.main()
