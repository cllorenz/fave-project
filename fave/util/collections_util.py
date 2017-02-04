#!/usr/bin/env python2

def dict_sub(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    common = [k for k in d1 if k in d2]
    return {k:v for k,v in d1 if not k in common}        

def list_sub(l1,l2):
    assert(type(d1) == dict and type(d2) == dict)
    return [e for e in l1 if not e in l2]

"""
def diff_dicts(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    common = [k for k in d1 if k in d2]
    uncommon = {k:v for k,v in d1+d2 if not (k in common)}
    uncommon += {k:v for k,v in common if d1[k] == d2[k]}
    return uncommon

def diff_lists(l1,l2):
    assert(type(l1) == list and type(l2) == list)

    common = [e for e in l1 if e in l2]
    return [e for e in d1+d2 if not (e in common)]

def intersect_dicts(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    return {k:v for k,v in d1 if k in d2 and d1[k] == d2[k]}

def intersect_lists(l1,l2):
    assert(type(l1) == list and type(l2) == list)
    return [e for e in l1 if e in l2]
"""
