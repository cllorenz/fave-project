#!/usr/bin/env python2

def dict_sub(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    common = [k for k in d1 if k in d2]
    return {k:d1[k] for k in d1 if not k in common}        

def dict_diff(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    return dict_sub(dict_union(d1,d2),dict_isect(d1,d2))

def dict_isect(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    return dict_sub(d1,dict_sub(d2,d1))

def dict_union(d1,d2):
    assert(type(d1) == dict and type(d2) == dict)
    keys = d1.keys()++d2.keys()
    return {k:d1[k] if k in d1 else d2[k] for k in keys}


def list_sub(l1,l2):
    assert(type(l1) == list and type(l2) == list)
    return [e for e in l1 if not e in l2]

def list_diff(l1,l2):
    assert(type(l1) == list and type(l2) == list)
    return list_sub(list_union(l1,l2),list_isect(l1,l2))

def list_isect(l1,l2):
    assert(type(l1) == list and type(l2) == list)
    return [e for e in l1 if e in l2]

def list_union(l1,l2):
    assert(type(l1) == list and type(l2) == list)
    lall = l1++l2
    isect = list_isect(l1,l2)
    return isect++[e for e in lall if not e in isect]
