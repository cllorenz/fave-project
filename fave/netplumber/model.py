#!/usr/bin/env python2

import json
from util.collections_util import list_sub,dict_sub


class Model(object):
    def __init__(self,node,type="model",tables={},ports={},wiring=[],mapping=None):
        self.node = node
        self.type = type
        self.tables = tables
        self.ports = ports
        self.wiring = wiring
        self.mapping = mapping

    def __str__(self):
        return "node: %s\ntype: %s\ntables:\n\t%s\nports:\n\t%s\nwiring:\n\t%s" % (
            self.node,
            self.type,
            self.tables,
            self.ports,
            self.wiring
        )

    def to_json(self):
        model = {
            "node" : self.node,
            "type" : self.type,
            "tables" : self.tables,
            "ports" : self.ports,
            "wiring" : self.wiring,
            "mapping" : self.mapping.to_json()
        }

        return json.dumps(model)

    @staticmethod
    def from_string(s):
        assert(type(s) == str)

        j = json.loads(s)
        return from_json(j)


    @staticmethod
    def from_json(j):
        return Model(
            j["node"],
            j["type"],
            tables=j["tables"],
            ports=j["ports"],
            wiring=[(p1,p2) for p1,p2 in j["wiring"]],
            mapping=Mapping(j["mapping"])
        )

    @staticmethod
    def from_string(s):
        j = json.loads(s)
        try:
            return {
                "model" : Model
            }[j["type"]].from_json(j)
        except KeyError:
            raise Exception("model type not implemented")


    def __sub__(self,other):
        assert(self.node == other.node)
        assert(self.type == other.type)

        tables = dict_sub(self.tables,other.tables)
        ports = dict_sub(self.ports,other.ports)
        wiring = list_sub(self.wiring,other.wiring)
        mapping = self.mapping + other.mapping

        return Model(self.node,self.type,tables,ports,wiring,mapping)

    """
    def diff(self,other):
        assert(self.node == other.node)
        assert(self.type == other.type)

        tables = diff_dicts(self.tables,other.tables)
        ports  = diff_dicts(self.ports,other.ports)
        wiring = diff_lists(self.wiring,other.wiring)
        mapping = self.mapping.diff(other.mapping)

    def intersect(self,other):
        assert(type(other) == Model)
        assert(self.node == other.node)
        assert(self.type == other.type)

        tables = intersect_dicts(self.tables,other.tables)
        ports = intersect_dicts(self.ports,other.ports)
        wiring = intersect_lists(self.wiring,other.wiring)
        mapping = self.mapping.intersect(other.mapping)
    """
