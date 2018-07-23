#!/usr/bin/env python2

def _ordered(obj):
    if isinstance(obj,dict):
        return sorted({k:_ordered(v) for k,v in obj.items()})
    elif isinstance(obj,list):
        return [_ordered(x) for x in obj]
    else:
        return obj

def equal(a,b):
    return _ordered(a) == _ordered(b)
