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

""" This module tests data structures representing models, header mappings,
    vectors, and headerspaces suitable for NetPlumber.
"""

import unittest

from netplumber.mapping import Mapping
from netplumber.vector import Vector, HeaderSpace
from netplumber.vector import get_field_from_vector, set_field_in_vector
from netplumber.vector import copy_field_between_vectors
from netplumber.vector import intersect_vectors, align_vector, align_headerspace
from devices.abstract_device import AbstractDeviceModel


class TestMapping(unittest.TestCase):
    """ This class tests header field mappings.
    """

    def setUp(self):
        """ Sets up a clean test environment.
        """
        self.mapping = Mapping()


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.mapping


    def test_cmp(self):
        """ Basic test for comparing mappings.
        """
        self.assertEqual(self.mapping, Mapping())


    def test_extend(self):
        """ Tests an extension of mappings.
        """

        self.mapping.extend('packet.ipv6.source')
        self.assertEqual(self.mapping.length, 128)
        self.assertEqual(list(self.mapping.keys()), ['packet.ipv6.source'])
        self.assertEqual(list(self.mapping.values()), [0])


    def test_expand(self):
        """ Tests the expansion of a mapping with another.
        """

        self.mapping.extend('packet.ipv6.source')
        other = Mapping(
            length=128, mapping={'packet.ipv6.destination' : 0}
        )
        self.mapping.expand(other)
        self.assertEqual(
            self.mapping,
            Mapping(
                length=256,
                mapping={'packet.ipv6.source':0, 'packet.ipv6.destination':128}
            )
        )


    def test_add(self):
        """ Tests the adding of one mapping to another.
        """

        self.mapping.extend('packet.ipv6.source')
        other = Mapping(
            length=128, mapping={'packet.ipv6.destination':0}
        )
        self.assertEqual(
            self.mapping + other,
            Mapping(
                length=256,
                mapping={'packet.ipv6.source':0, 'packet.ipv6.destination':128}
            )
        )


    def test_to_json(self):
        """ Tests the conversion of a mapping to JSON.
        """

        self.mapping.extend('packet.ipv6.source')
        self.assertEqual(
            self.mapping.to_json(), {'length' : 128, 'packet.ipv6.source' : 0}
        )


    def test_from_json(self):
        """ Tests the creation of a mapping from JSON.
        """

        self.mapping.extend('packet.ipv6.source')
        self.assertEqual(
            Mapping.from_json({'length' : 128, 'packet.ipv6.source' : 0}),
            self.mapping
        )


class TestVector(unittest.TestCase):
    """ This class tests vector handling.
    """

    def setUp(self):
        """ Sets up a clean test environment.
        """
        self.vector = Vector()


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.vector


    def test_enlarge(self):
        """ Tests the enlargement of a vector.
        """

        self.vector.enlarge(128)
        self.assertEqual(self.vector.length, 128)
        self.assertEqual(self.vector.vector, 'x'*128)


    def test_setitem(self):
        """ Tests setting a value in a vector.
        """

        self.vector.enlarge(128)
        self.vector[0:32] = '%s%s' % ('1'*16, '0'*16)
        self.assertEqual(self.vector.length, 128)
        self.assertEqual(len(self.vector.vector), 128)
        self.assertEqual(self.vector.vector, '%s%s%s' % ('1'*16, '0'*16, 'x'*96))


    def test_getitem(self):
        """ Tests reading a value from a vector
        """

        self.vector.enlarge(128)
        self.vector[0:32] = '%s%s' % ('1'*16, '0'*16)
        self.assertEqual(self.vector[8:24], '%s%s' % ('1'*8, '0'*8))
        self.assertEqual(self.vector[120:128], 'x'*8)


    def test_get_field_from_vector(self):
        """ Tests reading a field from a vector.
        """

        mapping = Mapping()
        mapping.extend('packet.ipv6.source')
        mapping.extend('packet.ipv6.destination')

        self.vector.enlarge(mapping.length)

        set_field_in_vector(
            mapping,
            self.vector,
            'packet.ipv6.source', '%s%s%s' % ('1'*16, '0'*16, 'x'*96)
        )
        self.assertEqual(self.vector.length, 256)
        self.assertEqual(len(self.vector.vector), mapping.length)
        self.assertEqual(self.vector.length, mapping.length)
        self.assertEqual(self.vector.vector, '%s%s%s' % ('1'*16, '0'*16, 'x'*224))


    def test_set_field_in_vector(self):
        """ Tests setting a field in a vector
        """

        mapping = Mapping()
        mapping.extend('packet.ipv6.source')
        mapping.extend('packet.ipv6.destination')
        self.vector.enlarge(mapping.length)
        set_field_in_vector(
            mapping,
            self.vector,
            'packet.ipv6.source', '%s%s%s' % ('1'*16, '0'*16, 'x'*96)
        )

        self.assertEqual(
            get_field_from_vector(
                mapping,
                self.vector,
                'packet.ipv6.source'
            ),
            '%s%s%s' % ('1'*16, '0'*16, 'x'*96)
        )
        self.assertEqual(
            get_field_from_vector(
                mapping,
                self.vector,
                'packet.ipv6.destination'
            ), 'x'*128)


    def test_copy_field_between_vectors(self):
        """ Tests copying from a vector to another.
        """

        map1 = Mapping()
        map1.extend('packet.ipv6.source')
        map1.extend('packet.ipv6.destination')

        map2 = Mapping()
        map2.extend('packet.ipv6.destination')
        map2.extend('packet.ipv6.source')

        self.vector.enlarge(map1.length)

        other = Vector()
        other.enlarge(map2.length)

        set_field_in_vector(
            map1,
            self.vector,
            'packet.ipv6.source', '%s%s%s' % ('1'*16, '0'*16, 'x'*96)
        )

        copy_field_between_vectors(
            map1, map2, self.vector, other, 'packet.ipv6.source'
        )

        self.assertEqual(
            get_field_from_vector(map1, self.vector, 'packet.ipv6.source'),
            get_field_from_vector(map2, other, 'packet.ipv6.source')
        )


class TestHeaderSpace(unittest.TestCase):
    """ This class tests header space structures.
    """

    def setUp(self):
        """ Provides a clean test environment.
        """
        vector = Vector(128)
        vector[0:128] = '%s%s%s' % ('1'*16, '0'*16, 'x'*96)
        self.header = HeaderSpace(vector.length, [vector])


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.header


    def test_enlarge(self):
        """ Tests the enlargement of a header space
        """

        self.header.enlarge(128)

        self.assertEqual(self.header.length, 256)
        self.assertTrue(all([v.length == 256 for v in self.header.hs_list]))
        self.assertTrue(all([v.length == 256 for v in self.header.hs_diff]))


    def test_to_json(self):
        """ Tests the conversion of a header space to JSON.
        """

        self.assertEqual(
            self.header.to_json(),
            {
                'length':128,
                'hs_list':['%s%s%s' % ('1'*16, '0'*16, 'x'*96)],
                'hs_diff':[]
            }
        )


    def test_from_json(self):
        """ Tests the creation of a header space from JSON.
        """

        self.assertEqual(
            HeaderSpace.from_json({
                'length':128,
                'hs_list':['%s%s%s' % ('1'*16, '0'*16, 'x'*96)],
                'hs_diff':[]
            }),
            self.header
        )


class TestModel(unittest.TestCase):
    """ This class provides tests for NetPlumber models.
    """

    def setUp(self):
        """ Provides a clean test environment.
        """
        self.model = AbstractDeviceModel(
            'foo',
            tables={'foo.1' : []},
            ports={'foo.1' : 'foo.1', 'foo.2' : 'foo.1'}
        )


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a model to JSON.
        """

        self.assertEqual(
            self.model.to_json(),
            {
                'node' : 'foo',
                'type' : 'model',
                'tables' : {'foo.1' : []},
                'ports' : {'foo.1' : 'foo.1', 'foo.2' : 'foo.1'},
                'wiring' : []
            }
        )


    def test_to_json_str(self):
        """ Tests the conversion of a model to a JSON string.
        """
        self.assertEqual(
            self.model.to_json_str(), \
'{\
"node": "foo", \
"type": "model", \
"tables": {"foo.1": []}, \
"ports": {"foo.1": "foo.1", "foo.2": "foo.1"}, \
"wiring": []\
}'
        )


    def test_from_json(self):
        """ Tests the creation of a model from JSON.
        """

        self.assertEqual(
            AbstractDeviceModel.from_json({
                'node' : 'foo',
                'type' : 'model',
                'tables' : {'foo.1' : []},
                'ports' : {'foo.1' : 'foo.1', 'foo.2' : 'foo.1'},
                'wiring' : []
            }),
            self.model
        )


    def test_from_json_str(self):
        """ Tests the creation of a model from a JSON string.
        """

        self.assertEqual(
            AbstractDeviceModel.from_string(
                '{\
                    "node":"foo", \
                    "raw_line" : null, \
                    "raw_line_no" : null, \
                    "type":"model", \
                    "tables":{"foo.1":[]}, \
                    "ports":{"foo.1":"foo.1", "foo.2":"foo.1"}, \
                    "wiring":[] \
                }'
            ),
            self.model
        )


    def test_eq_rejects_foreign_type(self):
        """ Comparing a device model to a foreign type is False, not a crash. """
        self.assertFalse(self.model == 'foo')
        self.assertTrue(self.model != 42)
        self.assertFalse(self.model == None)  # noqa: E711


    def test_sub(self):
        """ Tests the subtraction of a model from another.
        """

        other = AbstractDeviceModel(
            'foo',
            tables={'foo.1' : []},
            ports={'foo.1' : 'foo.1'}
        )

        result = AbstractDeviceModel(
            'foo',
            tables={},
            ports={'foo.2' : 'foo.1'}
        )

        self.assertEqual(self.model - other, result)


class TestIntersectVectors(unittest.TestCase):
    """ Tests the pure wildcard-intersection of two vector strings.

    intersect_vectors is the mathematical core of header-space verification:
    per position x ∩ b = b, b ∩ b = b, and 0 ∩ 1 = empty (None).
    """

    def test_identity_all_x(self):
        """ Intersecting all-x with anything yields the other operand. """
        self.assertEqual(intersect_vectors('xxxx', '10xx'), '10xx')
        self.assertEqual(intersect_vectors('10xx', 'xxxx'), '10xx')

    def test_equal_vectors(self):
        """ Intersecting a vector with itself is the identity. """
        self.assertEqual(intersect_vectors('1010', '1010'), '1010')
        self.assertEqual(intersect_vectors('xxxx', 'xxxx'), 'xxxx')

    def test_x_refines_to_bit(self):
        """ x on either side takes the concrete bit from the other side. """
        self.assertEqual(intersect_vectors('1x0x', 'x1x0'), '1100')

    def test_empty_intersection_returns_none(self):
        """ A 0-vs-1 conflict at any position yields the empty set (None). """
        self.assertIsNone(intersect_vectors('1010', '1011'))
        self.assertIsNone(intersect_vectors('0', '1'))
        self.assertIsNone(intersect_vectors('1xxx', '0xxx'))

    def test_single_position(self):
        """ Truth table on length-1 vectors. """
        self.assertEqual(intersect_vectors('x', '0'), '0')
        self.assertEqual(intersect_vectors('x', '1'), '1')
        self.assertEqual(intersect_vectors('x', 'x'), 'x')
        self.assertEqual(intersect_vectors('0', '0'), '0')
        self.assertEqual(intersect_vectors('1', '1'), '1')
        self.assertIsNone(intersect_vectors('0', '1'))

    def test_length_mismatch_asserts(self):
        """ Intersecting vectors of differing length is a contract violation. """
        with self.assertRaises(AssertionError):
            intersect_vectors('10', '101')


class TestVectorStatics(unittest.TestCase):
    """ Tests Vector.is_vector and Vector.from_vector_str. """

    def test_is_vector_accepts_vector_instance(self):
        self.assertTrue(Vector.is_vector(Vector(8)))

    def test_is_vector_accepts_valid_string(self):
        self.assertTrue(Vector.is_vector('01x01x'))

    def test_is_vector_rejects_bad_character(self):
        self.assertFalse(Vector.is_vector('01z'))

    def test_is_vector_rejects_non_string(self):
        self.assertFalse(Vector.is_vector(123))

    def test_is_vector_respects_field_length(self):
        """ With a field name, the length must match FIELD_SIZES[name]. """
        self.assertTrue(Vector.is_vector('x'*8, name='related'))
        self.assertFalse(Vector.is_vector('x'*7, name='related'))

    def test_from_vector_str_strips_commas(self):
        """ Comma group separators are stripped before parsing. """
        vec = Vector.from_vector_str('1010,0101')
        self.assertEqual(vec.vector, '10100101')
        self.assertEqual(vec.length, 8)


class TestAlignVector(unittest.TestCase):
    """ Tests realigning vectors/header spaces between reordered mappings.

    align_vector reconciles a vector laid out for one mapping to the bit layout
    of another; an offset error here would mislabel packet-header bits.
    """

    def setUp(self):
        # Two 8-bit fields in opposite order between the two mappings.
        self.map1 = Mapping()
        self.map1.extend('related')              # offset 0 in map1
        self.map1.extend('packet.ipv6.proto')    # offset 8 in map1

        self.map2 = Mapping()
        self.map2.extend('packet.ipv6.proto')    # offset 0 in map2
        self.map2.extend('related')              # offset 8 in map2

        self.vector = Vector(self.map1.length)
        set_field_in_vector(self.map1, self.vector, 'related', '11110000')
        set_field_in_vector(self.map1, self.vector, 'packet.ipv6.proto', '00001111')

    def test_align_vector_preserves_field_values(self):
        """ Field values survive the realignment, by field name. """
        aligned = align_vector(self.map1, self.map2, self.vector)
        self.assertEqual(
            get_field_from_vector(self.map2, aligned, 'related'), '11110000'
        )
        self.assertEqual(
            get_field_from_vector(self.map2, aligned, 'packet.ipv6.proto'), '00001111'
        )

    def test_align_vector_reorders_raw_bits(self):
        """ The raw bit layout follows the target mapping (proto then related). """
        aligned = align_vector(self.map1, self.map2, self.vector)
        self.assertEqual(aligned.vector, '00001111' + '11110000')

    def test_align_headerspace_realigns_each_vector(self):
        """ align_headerspace applies align_vector across the whole space. """
        hspace = HeaderSpace(self.map1.length, [self.vector])
        aligned = align_headerspace(self.map1, self.map2, hspace)
        self.assertEqual(aligned.hs_list[0].vector, '00001111' + '11110000')


if __name__ == '__main__':
    unittest.main()
