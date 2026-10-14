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

""" Tests for the parts of netplumber.mapping and netplumber.vector that
test_netplumber.py leaves out: the string forms, `Mapping.__cmp__`, the
no-op paths of extend/expand, `HeaderSpace.from_str`, a header space's diff
through JSON and alignment, and `HeaderSpace.pprint`.
"""

import contextlib
import io
import unittest

from netplumber.mapping import Mapping
from netplumber.vector import (
    HeaderSpace, Vector, align_headerspace, set_field_in_vector
)

_SRC = 'packet.ipv4.source'
_DST = 'packet.ipv4.destination'


def _vec(bits):
    return Vector.from_vector_str(bits)


class TestMappingExtras(unittest.TestCase):
    """ Mapping string form, comparison and idempotent growth. """

    def test_str_names_length_and_fields(self):
        text = str(Mapping(32, {_DST: 0}))
        self.assertTrue(text.startswith("length: 32,  mapping:"))
        self.assertIn(_DST, text)

    def test_cmp_checks_type_length_and_fields(self):
        mapping = Mapping(32, {_DST: 0})
        self.assertTrue(mapping.__cmp__(Mapping(32, {_DST: 0})))
        self.assertFalse(mapping.__cmp__({_DST: 0}))
        self.assertFalse(mapping.__cmp__(Mapping(64, {_DST: 0})))
        self.assertFalse(mapping.__cmp__(Mapping(32, {_SRC: 0})))

    def test_equality_ignores_length(self):
        """ Pinned: `==` is dict equality (Python 3 never calls `__cmp__`), so
        two mappings with the same fields but different lengths are equal. """
        self.assertEqual(Mapping(32, {_DST: 0}), Mapping(64, {_DST: 0}))

    def test_extending_by_a_known_field_changes_nothing(self):
        mapping = Mapping(32, {_DST: 0})
        mapping.extend(_DST)
        self.assertEqual((mapping.length, dict(mapping)), (32, {_DST: 0}))

    def test_expanding_by_an_equal_mapping_changes_nothing(self):
        mapping = Mapping(32, {_DST: 0})
        mapping.expand(Mapping(32, {_DST: 0}))
        self.assertEqual(mapping.length, 32)


class TestVectorAndHeaderSpaceExtras(unittest.TestCase):
    """ String forms, from_str and the diff half of a header space. """

    def test_vector_str(self):
        self.assertEqual(str(_vec("1x0")), "vector:\n\t1x0\nlength:\n\t3")

    def test_from_str_list_only(self):
        hspace = HeaderSpace.from_str("(10xx + 0x1x)\n")
        self.assertEqual(hspace.length, 4)
        self.assertEqual([v.vector for v in hspace.hs_list], ["10xx", "0x1x"])
        self.assertEqual(hspace.hs_diff, [])

    def test_from_str_with_diff(self):
        hspace = HeaderSpace.from_str("(1xxx) - (10xx + 1,1,0,0)")
        self.assertEqual([v.vector for v in hspace.hs_list], ["1xxx"])
        self.assertEqual([v.vector for v in hspace.hs_diff], ["10xx", "1100"])

    def test_from_str_rejects_two_differences(self):
        with self.assertRaises(Exception) as ctx:
            HeaderSpace.from_str("(1x) - (10) - (11)")
        self.assertIn("Cannot parse HeaderSpace", str(ctx.exception))

    def test_enlarge_reaches_the_diff(self):
        hspace = HeaderSpace(2, [_vec("1x")], [_vec("10")])
        hspace.enlarge(2)
        self.assertEqual((len(hspace), hspace.hs_diff[0].vector), (4, "10xx"))

    def test_json_round_trip_keeps_the_diff(self):
        hspace = HeaderSpace(4, [_vec("1xxx")], [_vec("10xx"), _vec("111x")])
        back = HeaderSpace.from_json(hspace.to_json())
        self.assertEqual(back, hspace)
        self.assertEqual([v.vector for v in back.hs_diff], ["10xx", "111x"])

    def test_align_headerspace_moves_the_diff_too(self):
        """ Fields keep their values when a header space is re-laid out for a
        mapping that puts them elsewhere -- in the diff as in the list. """
        source = Mapping(64, {_SRC: 0, _DST: 32})
        target = Mapping(64, {_DST: 0, _SRC: 32})
        src_bits, dst_bits = "1" * 32, "0" * 32
        vector = Vector(64)
        set_field_in_vector(source, vector, _SRC, src_bits)
        set_field_in_vector(source, vector, _DST, dst_bits)

        aligned = align_headerspace(
            source, target, HeaderSpace(64, [Vector(64)], [vector]))
        self.assertEqual(aligned.hs_diff[0].vector, dst_bits + src_bits)
        self.assertEqual(aligned.hs_list[0].vector, "x" * 64)


class TestHeaderSpacePprint(unittest.TestCase):
    """ pprint renders the determined fields of each vector by name. """

    def setUp(self):
        self.mapping = Mapping(64, {_SRC: 0, _DST: 32})

    def _vector(self, src=None, dst=None):
        vector = Vector(64)
        if src:
            set_field_in_vector(self.mapping, vector, _SRC, src)
        if dst:
            set_field_in_vector(self.mapping, vector, _DST, dst)
        return vector

    def _print(self, hspace):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hspace.pprint(self.mapping)
        return out.getvalue()

    def test_list_and_diff_are_rendered(self):
        """ Pinned: each part prints as a TUPLE repr -- a Python 2 `print`
        statement converted with parentheses. """
        ten_net = "00001010" + "x" * 24
        host = "00001010" + "0" * 23 + "1"
        hspace = HeaderSpace(64, [self._vector(src=ten_net, dst=host)],
                             [self._vector(dst=host)])
        text = self._print(hspace)
        self.assertEqual(text.splitlines(), [
            "('hs_list:', '%s = 10.0.0.0/8, %s = 10.0.0.1')" % (_SRC, _DST),
            "('hs_diff:', '%s = 10.0.0.1')" % _DST,
        ])

    def test_wildcard_vectors_and_an_empty_diff_print_only_the_list(self):
        text = self._print(HeaderSpace(64, [self._vector()]))
        self.assertEqual(text, "('hs_list:', '')\n")

    def test_a_mapping_is_required(self):
        with self.assertRaises(AssertionError):
            HeaderSpace(0, []).pprint()


if __name__ == '__main__':
    unittest.main()
