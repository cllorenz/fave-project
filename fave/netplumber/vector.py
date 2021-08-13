#!/usr/bin/env python2

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

""" This module provides data structures and methods for storing and manipulating
    vectors as well as header spaces.
"""

import json
from netplumber.mapping import FIELD_SIZES

def align_headerspace(smapping, tmapping, hspace):
    """ Aligns a headerspace to conform a target mapping.

    Keyword arguments:
    dmapping - the destination mapping
    smapping - the source mapping
    hspace - the headerspace to be aligned
    """

    hs_list = []
    for vector in hspace.hs_list:
        hs_list.append(align_vector(smapping, tmapping, vector))

    hs_diff = []
    for vector in hspace.hs_diff:
        hs_diff.append(align_vector(smapping, tmapping, vector))

    return HeaderSpace(tmapping.length, hs_list, hs_diff)


def align_vector(smapping, tmapping, vector):
    """ Aligns a vector to conform a target mapping.

    Keyword arguments:
    dmapping - the destination mapping
    smapping - the source mapping
    hspace - the headerspace to be aligned
    """

    vec = Vector(tmapping.length)
    for fld in smapping:
        copy_field_between_vectors(smapping, tmapping, vector, vec, fld)

    return vec


def copy_field_between_vectors(s_map, t_map, s_vec, t_vec, field):
    """ Copies a field from one vector to another respecting their mappings.

    Keyword arguments:
    s_map -- the mapping of the source vector
    t_map -- the mapping of the target vector
    s_vec -- the source vector
    t_vec -- the target vector
    field -- the copied field
    """

    value = get_field_from_vector(s_map, s_vec, field)
    set_field_in_vector(t_map, t_vec, field, value)


def get_field_from_vector(mapping, vector, field):
    """ Retrieves field value from vector.

    Keyword arguments:
    mapping -- the vector's mapping
    vector -- the vector
    value -- the requested field
    """

    start = mapping[field]
    stop = start + FIELD_SIZES[field]
    return vector[start:stop]


def set_field_in_vector(mapping, vector, field, value):
    """ Sets a field in a vector.

    Keyword arguments:
    mapping -- the vector's mapping
    vector -- the vector
    field -- the field to be set
    value -- the value to be set
    """

    start = mapping[field]
    stop = start + FIELD_SIZES[field]
    vector[start:stop] = value


def intersect_vectors(vec1, vec2):
    assert len(vec1) == len(vec2)

    res = ''

    for idx in range(len(vec1)):
        bit1 = vec1[idx]
        bit2 = vec2[idx]
        if bit1 == 'x': res += bit2
        elif bit2 == 'x': res += bit1
        elif bit1 == bit2: res += bit1
        else:
            return None

    return res


class Vector(object):
    """ This class stores vectors.
    """

    def __init__(self, length=0, preset="x"):
        """ Constructs a vector of a certain length and presetting.

        Keyword arguments:
        length -- the vector's initial length
        preset -- the vector's initial setting (may be: "0", "1", "x")
        """

        assert length >= 0 and preset in ["0", "1", "x"]

        self.length = length
        self.vector = preset*length


    @staticmethod
    def is_vector(vectors, name=None):
        """ Checks whether a string represents a vector.

        Keyword arguments:
        vectors - a string to be checked
        """

        if isinstance(vectors, Vector):
            return True

        if not isinstance(vectors, str):
            return False

        if name and len(vectors) != FIELD_SIZES[name]:
            return False

        for bit in vectors:
            if bit not in ['0', '1', 'x']:
                return False
        return True


    @staticmethod
    def from_vector_str(vectors):
        """ Creates a vector from a vector string.

        Keyword arguments:
        vectors - a vector string
        """

        vectors = str(vectors.replace(",", ""))

        assert Vector.is_vector(vectors)

        vlen = len(vectors)
        vec = Vector(vlen)
        vec.vector = vectors

        return vec


    def enlarge(self, size):
        """ Enlarges the vector.

        Keyword arguments:
        size -- the length added to the vector
        """
        self.length += size
        self.vector += "x"*size


    def __setitem__(self, key, value):
        assert isinstance(key, slice)
        start = key.start if key.start else 0
        stop = key.stop if key.stop else self.length
        before = self.vector[:start]
        after = self.vector[stop:]
        self.vector = before + value + after

        assert len(self.vector) == self.length


    def __getitem__(self, key):
        assert isinstance(key, slice)
        return self.vector[key]


    def __str__(self):
        return "vector:\n\t%s\nlength:\n\t%s" % (self.vector, self.length)


    def __len__(self):
        return self.length

    def __eq__(self, other):
        assert isinstance(other, Vector)
        return self.length == other.length and self.vector == other.vector


class HeaderSpace(object):
    """ This class stores header spaces.
    """

    def __init__(self, length, hs_list, hs_diff=None):
        """ Constructs a header space object.

        Keyword arguments:
        length -- the header spaces initial length
        hs_list -- a list of vectors representing the emitting header space
        hs_diff -- a list of vectors subtracted from the emitted header space
        """

        if hs_diff is None:
            hs_diff = []

        chk_type = lambda x: isinstance(x, Vector)
        assert all([chk_type(x) for x in hs_list]) and \
            all([chk_type(x) for x in hs_diff])

        chk_len = lambda x: len(x) == length
        assert length >= 0 and \
            all([chk_len(x) for x in hs_list]) and \
            all([chk_len(x) for x in hs_diff])

        self.length = length
        self.hs_list = hs_list
        self.hs_diff = hs_diff


    def enlarge(self, size):
        """ Enlarges the vectors in the header space.

        Keyword arguments:
        size -- the length added to the header space
        """

        self.length += size
        for vec in self.hs_list:
            vec.enlarge(size)
        for vec in self.hs_diff:
            vec.enlarge(size)


    def __len__(self):
        return self.length


    @staticmethod
    def from_str(s):
        lists = s.rstrip('\n').split(' - ')
        hsd = None
        if len(lists) == 1:
            hsl = lists.pop()
        elif len(lists) == 2:
            hsl, hsd = lists
        else:
            raise Exception("Cannot parse HeaderSpace: %s" % s)

        hsl = hsl.lstrip('(').rstrip(')')
        if hsd: hsd = hsd.lstrip('(').rstrip(')')

        hs_list = [Vector.from_vector_str(vs) for vs in hsl.split(' + ')]
        hs_diff = []
        if hsd: hs_diff = [Vector.from_vector_str(vs) for vs in hsd.split(' + ')]

        length = hs_list[0].length

        return HeaderSpace(length, hs_list, hs_diff)


    def to_json(self):
        """ Converts the header space to JSON.
        """

        return {
            "length" : self.length,
            "hs_list" : [v.vector for v in self.hs_list],
            "hs_diff" : [v.vector for v in self.hs_diff]
        }


    @staticmethod
    def from_json(j):
        """ Create a header space from JSON.

        Keyword arguments:
        j -- a header space represented as JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        length = int(j['length'])
        hs_list = []
        hs_diff = []

        for vector in j['hs_list']:
            vec = Vector(length)
            vec[:] = vector
            hs_list.append(vec)

        for vector in j['hs_diff']:
            vec = Vector(length)
            vec[:] = vector
            hs_diff.append(vec)

        return HeaderSpace(length, hs_list, hs_diff)


    def __eq__(self, other):
        assert isinstance(other, HeaderSpace)
        return all([
            self.length == other.length,
            self.hs_list == other.hs_list,
            self.hs_diff == other.hs_diff
        ])


    def pprint(self, mapping=None):
        from ip6np.ip6np_util import bitvector_to_field_value

        fields = list([f for f in mapping if f != 'length'])

        hsl = []
        for vector in self.hs_list:
            hslv = []
            for field in fields:
                value = bitvector_to_field_value(
                    get_field_from_vector(mapping, vector, field), field
                )
                if value:
                    hslv.append("%s = %s" % (field, value))
            if hslv:
                hsl.append(hslv)

        hsd = []
        for vector in self.hs_diff:
            hsdv = []
            for field in fields:
                value = bitvector_to_field_value(
                    get_field_from_vector(mapping, vector, field), field
                )
                if value:
                    hsdv.append("%s = %s" % (field, value))
            if hsdv:
                hsd.append(hsdv)


        print 'hs_list:', '\n + '.join([', '.join(hslv) for hslv in hsl])
        if hsd: print 'hs_diff:', '\n + '.join([', '.join(hsdv) for hsdv in hsd])
