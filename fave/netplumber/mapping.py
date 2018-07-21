#!/usr/bin/env python2

import json
#from util.collections_util import diff_dicts

field_sizes = {
    "packet.ether.source" : 48,
    "packet.ether.destination" : 48,
    "packet.ether.type" : 8,
    "packet.ipv6.source" : 128,
    "packet.ipv6.destination" : 128,
    "packet.ipv6.proto" : 8,
    #"packet.ipv6.priority":, # XXX maybe later
    "packet.ipv6.icmpv6.type" : 16,
    "packet.upper.dport" : 16,
    "packet.upper.sport" : 16,
    #"packet.upper.tcp.flags" : 8, # XXX maybe later
    #"packet.upper.tcp.syn" : 8, # XXX maybe later
    #"packet.upper.tcp.option" : , # XXX maybe later
    "module" : 8,
    "module.limit" : 32,
    "module.state" : 8,
    "module.ipv6header.header" : 8,
    "interface" : 16,
    "module.rt" : 8,
    "module.ipv6header.rt.type" : 8,
    "module.ipv6header.rt.segsleft" : 8,
    "module.ipv6header.rt.len" : 8,
    #"module.ipv6header.rt.0-res" :  # XXX maybe later
    #"module.ipv6header.rt.0-addrs" : # XXX maybe later
    #"module.ipv6header.rt.0-not-strict" : , # XXX maybe later
    "module.ipv6header.ah.spi" : 32,
    "module.ipv6header.ah.len" : 8,
    "module.ipv6header.ah.res" : 16,
    "module.ipv6header.dst.len" : 8,
    #"module.ipv6header.dst.opts" : ,
    "module.ipv6header.frag.id" : 32,
    #"module.ipv6header.frag.len" : ,
    "module.ipv6header.hbh.len" : 8,
    #"module.ipv6header.hbh.opts" : ,
    "module.ipv6header.hl.eq" : 8,
    "module.ipv6header.hl.lt" : 8,
    "module.ipv6header.hl.gt" : 8,
    "module.ipv6header.mh.type" : 8
}


class Mapping(dict):

    def __init__(self,length=0,mapping={}):
        super(Mapping,self).__init__(mapping)
        self.length = length

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
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

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
        mapping = Mapping(length=self.length,mapping=self)
        mapping.expand(other)
        return mapping


    def expand(self,other):
        assert(type(other) == Mapping)

        if self == other:
            return

        uncommon = [k for k in other if not (k in self)]
        for k in uncommon:
            self[k] = self.length
            self.length += field_sizes[k]

