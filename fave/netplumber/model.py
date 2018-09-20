#!/usr/bin/env python2

""" This module provides a basic node model to be stored in NetPlumber.
"""

import json
from util.collections_util import list_sub, dict_sub
from netplumber.mapping import Mapping


class Model(object):
    """ This class stores a basic model for a node.
    """

    def __init__(self, node, mtype="model", tables=None, ports=None, wiring=None, mapping=None):
        """ Constructs a basic NetPlumber model

        Keyword arguments:
        node -- the node's name
        type -- the model's type (default: "model")
        tables -- a list of tables storing rules
        ports -- a mapping of port lists to the model's tables
        wiring -- a list of unidirectional links between the model's ports
        mapping -- a mapping for the rule vectors
        """

        self.node = node
        self.type = mtype
        self.tables = tables if tables is not None else []
        self.ports = ports if ports is not None else {}
        self.wiring = wiring if wiring is not None else []
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


    def expand(self, mapping):
        """ Expands the models mapping as well as its vectors

        Keyword arguments:
        mapping - the extension mapping
        """
        assert isinstance(mapping, Mapping)

        self.mapping.expand(mapping)

        for table in self.tables:
            for rule in self.tables[table]:
                rule.enlarge(self.mapping.length)


    def to_json(self):
        """ Converts the model to a JSON object.
        """

        return {
            "node" : self.node,
            "type" : self.type,
            "tables" : self.tables,
            "ports" : self.ports,
            "wiring" : self.wiring,
            "mapping" : self.mapping.to_json()
        }


    def to_json_str(self):
        """ Converts the model to a JSON string.
        """
        return json.dumps(self.to_json())


    @staticmethod
    def from_string(jsons):
        """ Creates a model from a JSON string.

        Keyword arguments:
        jsons -- a JSON string
        """

        assert isinstance(jsons, str)

        j = json.loads(jsons)
        return Model.from_json(j)


    @staticmethod
    def from_json(j):
        """ Creates a model from a JSON object.

        Keyword arguments:
        j -- a JSON object
        """

        return Model(
            j["node"],
            j["type"],
            tables=j["tables"],
            ports=j["ports"],
            wiring=[(p1, p2) for p1, p2 in j["wiring"]],
            mapping=Mapping(j["mapping"])
        )


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        tables = {}
        for tab in self.tables:
            if tab in other.tables:
                table = list_sub(self.tables[tab], other.tables[tab])
                if table:
                    tables[tab] = table

        ports = dict_sub(self.ports, other.ports)
        wiring = list_sub(self.wiring, other.wiring)
        mapping = self.mapping + other.mapping

        return Model(
            self.node,
            mtype=self.type,
            tables=tables,
            ports=ports,
            wiring=wiring,
            mapping=mapping
        )


    def __eq__(self, other):
        assert isinstance(other, Model)
        return all([
            self.node == other.node,
            self.type == other.type,
            self.tables == other.tables,
            self.ports == other.ports,
            self.wiring == other.wiring,
            self.mapping == other.mapping
        ])
