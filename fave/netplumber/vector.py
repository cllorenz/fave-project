#!/usr/bin/env python2

from mapping import field_sizes


def copy_field_between_vectors(map1,map2,v1,v2,field):
    value = get_field_from_vector(map1,v1,field)
    set_field_in_vector(map2,v2,field,value)


def get_field_from_vector(mapping,vector,field):
    start = mapping[field]
    stop = start + field_sizes[field]
    return vector[start:stop]


def set_field_in_vector(mapping,vector,field,value):
    start = mapping[field]
    stop = start + field_sizes[field]
    vector[start:stop] = value


class Vector(object):
    def __init__(self,length=0,preset="x"):
        assert(length >= 0 and preset in ["0","1","x"])

        self.length = length
        self.vector = preset*length


    def enlarge(self,size):
        self.length += size
        self.vector += "x"*size


    def __setitem__(self,key,value):
        assert(isinstance(key,slice))
        start = key.start if key.start else 0
        stop = key.stop if key.stop else self.length
        a = self.vector[:start]
        b = self.vector[stop:]
        self.vector = a + value + b

        assert(len(self.vector) == self.length)


    def __getitem__(self,key):
        assert(isinstance(key,slice))
        return self.vector[key]


    def __str__(self):
        return "vector:\n\t%s\nlength:\n\t%s" % (self.vector,self.length)


    def __len__(self):
        return self.length


class HeaderSpace(object):
    def __init__(self,length,hs_list,hs_diff=[]):
        chk_type = lambda x: type(x) == Vector
        assert(all(map(chk_type,hs_list)) and all(map(chk_type,hs_diff)))
        chk_len = lambda x: len(x) == length
        assert(length >= 0 and all(map(chk_len,hs_list)) and all(map(chk_len,hs_diff)))


        self.length = length
        self.hs_list = hs_list
        self.hs_diff = hs_diff


    def enlarge(self,size):
        for v in self.hs_list:
            v.enlarge(size)
        for v in self.hs_diff:
            v.enlarge(size)


    def __len__(self):
        return self.length


    def to_json(self):
        return {
            "length" : self.length,
            "hs_list" : [v.vector for v in self.hs_list],
            "hs_diff" : [v.vector for v in self.hs_diff]
        }


    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        length = int(j['length'])
        hs_list = []
        hs_diff = []

        for vector in j['hs_list']:
            v = Vector(length)
            v[:] = vector
            hs_list.append(v)

        for vector in j['hs_diff']:
            v = Vector(length)
            v[:] = vector
            hs_diff.append(v)

        return HeaderSpace(length,hs_list,hs_diff)
