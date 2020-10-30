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

""" This module provides set operations for dicts and lists.
"""

def dict_sub(dct1, dct2):
    """ Subtracts a dict from another.

    Keyword arguments:
    dct1 -- a dictionary
    dct2 -- a dictionary to be subtracted
    """

    assert isinstance(dct1, dict) and isinstance(dct2, dict)
    common = [k for k in dct1 if k in dct2]
    return {k:dct1[k] for k in dct1 if k not in common}


def dict_diff(dct1, dct2):
    """ Returns the diff of two dicts.

    Keyword arguments:
    dct1 -- a dictionary
    dct2 -- a dictionary
    """

    assert isinstance(dct1, dict) and isinstance(dct2, dict)
    return dict_sub(dict_union(dct1, dct2), dict_isect(dct1, dct2))


def dict_isect(dct1, dct2):
    """ Intersects two dicts.

    Keyword arguments:
    dct1 -- a dictionary
    dct2 -- a dictionary
    """

    assert isinstance(dct1, dict) and isinstance(dct2, dict)
    common = [k for k in dct1 if k in dct2]
    return {k:dct1[k] for k in common}


def dict_union(dct1, dct2):
    """ Unions two dicts.

    Keyword arguments:
    dct1 -- a dictionary
    dct2 -- a dictionary
    """

    assert isinstance(dct1, dict) and isinstance(dct2, dict)
    keys = dct1.keys() + dct2.keys()
    return {k:dct1[k] if k in dct1 else dct2[k] for k in keys}


def list_sub(lst1, lst2):
    """ Subtracts a list from another.

    Keyword arguments:
    dct1 -- a list
    dct2 -- a list to be subtracted
    """

    assert isinstance(lst1, list) and isinstance(lst2, list)
    return [e for e in lst1 if e not in lst2]


def list_diff(lst1, lst2):
    """ Returns the diff of two lists.

    Keyword arguments:
    dct1 -- a list
    dct2 -- a list
    """

    assert isinstance(lst1, list) and isinstance(lst2, list)
    return list_sub(list_union(lst1, lst2), list_isect(lst1, lst2))


def list_isect(lst1, lst2):
    """ Intersects two lists.

    Keyword arguments:
    dct1 -- a list
    dct2 -- a list
    """

    assert isinstance(lst1, list) and isinstance(lst2, list)
    return [e for e in lst1 if e in lst2]


def list_union(lst1, lst2):
    """ Unions two lists.

    Keyword arguments:
    dct1 -- a list
    dct2 -- a list
    """

    assert isinstance(lst1, list) and isinstance(lst2, list)
    lall = lst1 + lst2
    isect = list_isect(lst1, lst2)
    return isect + [e for e in lall if e not in isect]
