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

""" This module provides utilities to handle JSON.
"""

import json

def _ordered(obj):
    res = obj

    if isinstance(obj, dict):
        res = sorted({k:_ordered(v) for k, v in obj.items()})
    elif isinstance(obj, list):
        res = [_ordered(x) for x in obj]

    return res


def equal(obj1, obj2):
    """ Checks whether two JSON objects are equal.
    """
    return _ordered(obj1) == _ordered(obj2)


def pstr(j):
    """ Returns a pretty JSON string.

    Keyword arguments:
    j -- a JSON string or object
    """

    if isinstance(j, str):
        j = json.loads(j)

    return json.dumps(j, sort_keys=True, indent=4, separators=(',', ': '))
