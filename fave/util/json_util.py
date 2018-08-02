#!/usr/bin/env python2

""" This module provides utilities to handle JSON.
"""

import json

def _ordered(obj):
    if isinstance(obj, dict):
        return sorted({k:_ordered(v) for k, v in obj.items()})
    elif isinstance(obj, list):
        return [_ordered(x) for x in obj]
    else:
        return obj

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
