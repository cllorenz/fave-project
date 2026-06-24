#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" This module provides a basic node model to be stored in NetPlumber.
"""

from __future__ import annotations

import json

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from util.collections_util import list_sub, dict_sub
from util.typing_util import JSONDict

if TYPE_CHECKING:
    from rule.rule_model import Rule


class AbstractDeviceModel(object):
    """ This class stores a basic model for a node.
    """

    def __init__(
            self,
            node: str,
            mtype: str = "model",
            tables: Optional[Dict[str, List["Rule"]]] = None,
            ports: Optional[Dict[str, Any]] = None,
            wiring: Optional[List[Tuple[str, str]]] = None
    ) -> None:
        """ Constructs a basic NetPlumber model.

        Keyword arguments:
        node -- the node's name
        type -- the model's type (default: "model")
        tables -- a list of tables storing rules
        ports -- a mapping of port lists to the model's tables
        wiring -- a list of unidirectional links between the model's ports
        """

        self.node = node
        self.type = mtype
        self.tables: Dict[str, List["Rule"]] = tables if tables is not None else {}
        self.ports: Dict[str, Any] = ports if ports is not None else {}
        self.wiring: List[Tuple[str, str]] = wiring if wiring is not None else []
        # keyed by table name on reset but by rule.tid (int or str) on insert
        self._adds: Dict[Any, List["Rule"]] = {t : [] for t in self.tables}
        self._deletes: List[int] = []


    def __str__(self) -> str:
        return "node: %s\ntype: %s\ntables:\n\t%s\nports:\n\t%s\nwiring:\n\t%s" % (
            self.node,
            self.type,
            self.tables,
            self.ports,
            self.wiring
        )


    def reset(self) -> None:
        """ Resets add and delete buffers.
        """
        self._adds = {t : [] for t in self.tables}
        self._deletes = []


    def add_rule(self, rule: "Rule") -> None:
        """ Add rule to add buffer.

        Positional arguments:
        rule -- the rule to be added
        """
        self.add_rules([rule])


    def add_rules(self, rules: Iterable["Rule"]) -> None:
        """ Add rules to rule buffer.

        Positional arguments:
        rules -- list of ports to be added
        """
        for rule in rules:
            self._adds.setdefault(rule.tid, [])
            self._adds[rule.tid].append(rule)


    def remove_rule(self, idx: int) -> None:
        """ Add rule to delete buffer.
        """
        self._deletes.append(idx)


    def ingress_port(self, port: str) -> str:
        """ Returns the model's corresponding ingress port.

        Keyword arguments:
        port -- the outer model's port identifier
        """
        return port


    def egress_port(self, port: str) -> str:
        """ Returns the model's corresponding egress port.

        Keyword arguments:
        port -- the outer model's port identifier
        """
        return port


    def table_index(self, table: str) -> int:
        """ Returns an unambigious index of an internal table.

        Keyword arguments:
        table -- The table's name
        """
        return sorted(self.tables.keys()).index(table)


    def port_index(self, port: str) -> int:
        """ Returns an unambigious index of a port of the model.

        Keyword arguments:
        port -- The port's name
        """
        return sorted(self.ports.keys()).index(port)


    def to_json(self) -> JSONDict:
        """ Converts the model to a JSON object.
        """

        return {
            "node" : self.node,
            "type" : self.type,
            "tables" : {
                tk:[
                    r.to_json() for r in t
                ]  for tk, t in list(self.tables.items())
            },
            "ports" : self.ports,
            "wiring" : self.wiring
        }


    def to_json_str(self) -> str:
        """ Converts the model to a JSON string.
        """
        return json.dumps(self.to_json())


    @staticmethod
    def from_string(jsons: str) -> "AbstractDeviceModel":
        """ Creates a model from a JSON string.

        Keyword arguments:
        jsons -- a JSON string
        """

        assert isinstance(jsons, str)

        j = json.loads(jsons)
        return AbstractDeviceModel.from_json(j)


    @staticmethod
    def from_json(j: JSONDict) -> "AbstractDeviceModel":
        """ Creates a model from a JSON object.

        Keyword arguments:
        j -- a JSON object
        """

        model = AbstractDeviceModel(
            j["node"],
            j["type"],
            tables=j["tables"],
            ports=j["ports"],
            wiring=[(p1, p2) for p1, p2 in j["wiring"]]
        )

        return model

    def __sub__(self, other: "AbstractDeviceModel") -> "AbstractDeviceModel":
        assert self.node == other.node
        assert self.type == other.type

        tables: Dict[str, List["Rule"]] = {}
        for tab in self.tables:
            if tab in other.tables:
                table = list_sub(self.tables[tab], other.tables[tab])
                if table:
                    tables[tab] = table

        ports = dict_sub(self.ports, other.ports)
        wiring = list_sub(self.wiring, other.wiring)

        return AbstractDeviceModel(
            self.node,
            mtype=self.type,
            tables=tables,
            ports=ports,
            wiring=wiring
        )


    def __eq__(self, other: object) -> bool:
        assert isinstance(other, AbstractDeviceModel)

        return all([
            self.node == other.node,
            self.type == other.type,
            self.tables == other.tables,
            self.ports == other.ports,
            self.wiring == other.wiring,
        ])

    def __ne__(self, other: object) -> bool:
        assert isinstance(other, AbstractDeviceModel)
        return not self == other
