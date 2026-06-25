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

""" Unit tests for the pure, backend-free helpers in netplumber.adapter.

These functions do the bit-packing that gives every NetPlumber table, port, and
rule its identity; a packing error silently corrupts the verification model, so
they are tested in isolation here (no socket / live backend needed).
"""

import unittest

from netplumber.adapter import (
    _calc_port, _calc_rule_index, _expand_field,
    _TABLE_IDX_MAX, _RULE_IDX_MAX, _NEG_IDX_MAX,
)
from devices.abstract_device import AbstractDeviceModel
from rule.rule_model import RuleField


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


if __name__ == '__main__':
    unittest.main()
