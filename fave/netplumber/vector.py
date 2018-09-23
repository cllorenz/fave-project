#!/usr/bin/env python2

""" This module provides data structures and methods for storing and manipulating
    vectors as well as header spaces.
"""

import json
from netplumber.mapping import FIELD_SIZES


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
    def is_vector(vectors):
        if isinstance(vectors, Vector):
            return True

        for bit in vectors:
            if bit not in ['0', '1', 'x']:
                return False
        return True


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
