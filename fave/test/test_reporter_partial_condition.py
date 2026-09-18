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

""" Rendering a condition the report cannot express as a single value.

`_parse_cond` turns a violation's condition vector back into readable
`field=value` pairs, and asserted that any field which is not all-`x` has a
concrete value:

    assert value is not None  # a non-all-x field has a concrete value

True for every condition the suite could previously produce -- a service's port
is exact -- and false by construction for a COMPLEMENT condition, whose vectors
pin one bit and wildcard the rest. Turning the complement check on made the
report task die with a bare AssertionError, losing the whole report for a run
whose compliance check had already completed successfully.

The third case is rendered as its bit pattern. It is less readable than a
number, but it is the truth about that flow, and a violation witness nobody can
see is worse than an ugly one.
"""

import unittest

from netplumber.mapping import Mapping
from netplumber.vector import Vector, set_field_in_vector
from reporting.reporter import _parse_cond


_DPORT = 'packet.upper.dport'
_PROTO = 'packet.ipv6.proto'


class TestParseCond(unittest.TestCase):

    def setUp(self):
        self.mapping = Mapping(0)
        self.mapping.extend(_PROTO)
        self.mapping.extend(_DPORT)

    def _vector(self, **fields):
        vector = Vector(self.mapping.length, preset='x')
        for name, bits in fields.items():
            set_field_in_vector(
                self.mapping, vector, {'dport': _DPORT, 'proto': _PROTO}[name],
                bits)
        return vector.vector

    def test_a_fully_determined_field_renders_as_its_value(self):
        rendered = dict(_parse_cond(
            self._vector(dport='{:016b}'.format(80)), self.mapping))

        self.assertEqual(rendered[_DPORT], '80')

    def test_an_all_wildcard_field_is_omitted(self):
        rendered = dict(_parse_cond(self._vector(), self.mapping))

        self.assertEqual(rendered, {})

    def test_a_PARTIALLY_determined_field_renders_as_its_pattern(self):
        """ The complement shape: one bit pinned, the rest free. """
        pattern = 'x' * 15 + '1'
        rendered = dict(_parse_cond(self._vector(dport=pattern), self.mapping))

        self.assertEqual(rendered[_DPORT], pattern)

    def test_a_partially_determined_field_does_not_raise(self):
        """ The regression: this used to abort the whole report task. """
        _parse_cond(self._vector(dport='x' * 8 + '1' + 'x' * 7), self.mapping)

    def test_a_mixed_condition_renders_both_kinds(self):
        rendered = dict(_parse_cond(
            self._vector(proto='{:08b}'.format(6), dport='x' * 15 + '0'),
            self.mapping))

        self.assertEqual(rendered[_PROTO], '6')
        self.assertEqual(rendered[_DPORT], 'x' * 15 + '0')


if __name__ == '__main__':
    unittest.main()
