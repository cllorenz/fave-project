#!/usr/bin/env python2

""" This module provides utilities to compare JSON objects.
"""

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
