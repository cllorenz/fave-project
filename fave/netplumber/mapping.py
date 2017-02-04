#!/usr/bin/env python2

import json
#from util.collections_util import diff_dicts

field_sizes = {
    "packet.ipv6.source":128,
    "packet.ipv6.destination":128,
    "packet.ipv6.proto":8,
    "packet.ipv6.icmpv6.type":16,
    "packet.upper.dport":16,
    "packet.upper.sport":16,
    "module":8,
    "module.limit":32,
    "module.state":8,
    "module.ipv6header.header":8,
    "interface":16,
}

class Mapping(dict):

    def __init__(self,length=0,mapping={}):
        super(Mapping,self).__init__(mapping)
        self.length = length
        self.move = []

    def __str__(self):
        return "length: %i, mapping:\n\t%s" % (
                self.length,
                super(dict,self).__str__()
            )

    def to_json(self):
        tmp = dict(self)
        tmp["length"] = self.length
        return tmp

    @staticmethod
    def from_string(s):
        j = json.loads(s)
        return from_json(j)

    @staticmethod
    def from_json(j):
        length = j["length"]
        del j["length"]
        return Mapping(length=length,mapping=j)


    def __cmp__(self,other):
        if type(other) != Mapping:
            return False
        if self.length != other.length:
            return False
        if not super(Mapping,self).__cmp__(super(Mapping,other)):
            return False
        return True

    def extend(self,field):
        self[field] = self.length
        self.length += field_sizes[field]


    """
    def diff(self,other):
        if self == other:
            return self

        mapping = diff_dicts(self,other)

        return Mapping(self.length,mapping=mapping)

    def intersect(self,other):
        if self == other
            return self

        mapping = intersect_dicts(self,other)

        return Mapping(self.length,mapping=mapping)
    """

    def __add__(self,other):
        if self == other:
            return

        uncommon = [k for k in other if not (k in self)]
        for k in uncommon:
            self[k] = self.length
            self.move.append((other.mapping[k],self.length))
            self.length += field_sizes[k]

