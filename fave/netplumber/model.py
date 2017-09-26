#!/usr/bin/env python2

import json
from util.collections_util import list_sub,dict_sub
from netplumber.mapping import Mapping


class Model(object):
    def __init__(self,node,type="model",tables={},ports={},wiring=[],mapping=None):
        self.node = node
        self.type = type
        self.tables = tables
        self.ports = ports
        self.wiring = wiring
        self.mapping = mapping

    def __str__(self):
        return "node: %s\ntype: %s\ntables:\n\t%s\nports:\n\t%s\nwiring:\n\t%s\nmapping:\n\t%s" % (
            self.node,
            self.type,
            self.tables,
            self.ports,
            self.wiring,
            self.mapping
        )

    def to_json(self):
        return {
            "node" : self.node,
            "type" : self.type,
            "tables" : self.tables,
            "ports" : self.ports,
            "wiring" : self.wiring,
            "mapping" : self.mapping.to_json()
        }

    def to_json_str(self):
        return json.dumps(self.to_json())

    @staticmethod
    def from_string(s):
        assert(type(s) == str)

        j = json.loads(s)
        return Model.from_json(j)

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

    """
    @staticmethod
    def from_string(s):
        j = json.loads(s)
        try:
            return {
                "model" : Model
            }[j["type"]].from_json(j)
        except KeyError:
            raise Exception("model type not implemented")
    """

    def __sub__(self,other):
        assert(self.node == other.node)
        assert(self.type == other.type)

        tables = {}
        for t in self.tables:
            if t in other.tables:
                table = list_sub(self.tables[t],other.tables[t])
                if table:
                    tables[t] = table

        ports = dict_sub(self.ports,other.ports)
        wiring = list_sub(self.wiring,other.wiring)
        mapping = self.mapping + other.mapping

        return Model(
            self.node,
            type=self.type,
            tables=tables,
            ports=ports,
            wiring=wiring,
            mapping=mapping
        )

    def __eq__(self,other):
        assert(type(other) == Model)
        return all([
            self.node == other.node,
            self.type == other.type,
            self.tables == other.tables,
            self.ports == other.ports,
            self.wiring == other.wiring,
            self.mapping == other.mapping
        ])

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
