#!/usr/bin/env python2

""" This module provides data structures for mappings of header fields.
"""

import json

FIELD_SIZES = {
    "packet.ether.source" : 48,
    "packet.ether.destination" : 48,
    "packet.ether.type" : 8,
    "packet.ether.vlan" : 16,
    "packet.ipv4.source" : 32,
    "packet.ipv4.destination" : 32,
    "packet.ipv6.source" : 128,
    "packet.ipv6.destination" : 128,
    "packet.ipv6.proto" : 8,
    #"packet.ipv6.priority" : ,
    "packet.ipv6.icmpv6.type" : 16,
    "packet.upper.dport" : 16,
    "packet.upper.sport" : 16,
    "packet.upper.tcp.flags" : 8,
    #"packet.upper.tcp.option" : ,
    "module" : 8,
    "module.limit" : 32,
    "module.state" : 8,
    "module.ipv6header.header" : 8,
    "interface" : 32,
    "module.rt" : 8,
    "module.ipv6header.rt.type" : 8,
    "module.ipv6header.rt.segsleft" : 8,
    "module.ipv6header.rt.len" : 8,
    #"module.ipv6header.rt.0-res" : ,
    #"module.ipv6header.rt.0-addrs" : ,
    #"module.ipv6header.rt.0-not-strict" : ,
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
    """ This class stores mappings of fields giving meaning to bits on a vector.
    """

    def __init__(self, length=0, mapping=None):
        """ Contructs a mapping object.

        Keyword arguments:
        length -- the total length of the fields chained on a vector
        mapping -- a predefined mapping stored as a dict
        """

        if mapping is None:
            mapping = {}

        super(Mapping, self).__init__(mapping)
        self.length = length


    def __str__(self):
        """ Provides a string representation of the mapping.
        """

        return "length: %i,  mapping:\n\t%s" % (
            self.length,
            super(Mapping, self).__str__()
        )


    def to_json(self):
        """ Converts the mapping to JSON.
        """

        tmp = dict(self)
        tmp["length"] = self.length
        return tmp


    @staticmethod
    def from_json(j):
        """ Constructs a mapping from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        length = j["length"]
        del j["length"]
        return Mapping(length=length, mapping=j)


    def __cmp__(self, other):
        """ Compares the mapping with another.

        Keyword arguments:
        other -- the compared mapping
        """

        if not isinstance(other, Mapping):
            return False
        if self.length != other.length:
            return False
        if not super(Mapping, self).__cmp__(super(Mapping, other)):
            return False
        return True


    def extend(self, field):
        """ Extends the mapping with a field.

        Keyword arguments:
        field -- the field identifier to extend the mapping
        """
        if field in self:
            return

        self[field] = self.length
        self.length += FIELD_SIZES[field]


    def __add__(self, other):
        """ Adds another mapping.

        Keyword arguments:
        other -- the added mapping
        """

        mapping = Mapping(length=self.length, mapping=self)
        mapping.expand(other)
        return mapping


    def expand(self, other):
        """ Expands the mapping by adding fields from another mapping.

        Keyword arguments:
        other -- the mapping providing fields to be added
        """

        assert isinstance(other, Mapping)

        if self == other:
            return

        uncommon = [k for k in other if k not in self]
        for k in uncommon:
            self[k] = self.length
            self.length += FIELD_SIZES[k]

