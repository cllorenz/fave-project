""" This module provides a flow generator model.
"""

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

from __future__ import annotations

import json

from typing import Dict, List, Optional, Union

from rule.rule_model import RuleField
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from util.typing_util import JSONDict

class GeneratorModel(object):
    """ This class provides a flow generator model.
    """

    def __init__(
            self, node: str,
            fields: Optional[Dict[str, List[RuleField]]] = None
    ) -> None:
        self.fields: Dict[str, List[RuleField]] = {
            OXM_FIELD_TO_MATCH_FIELD[name] : [
                RuleField(
                    OXM_FIELD_TO_MATCH_FIELD[f.name], f.value
                ) for f in field_list
            ] for name, field_list in list(fields.items())
        } if fields is not None else {}

        self.node = node
        self.type = "generator"
        self.ports = {node+'.1' : 1}


    def to_json(self) -> JSONDict:
        """ Converts the flow generator to JSON.
        """

        return {
            "fields" : {n:[f.to_json() for f in fl] for n, fl in list(self.fields.items())},
            "node" : self.node,
            "type" : self.type
        }

    @staticmethod
    def from_json(j: Union[str, JSONDict]) -> "GeneratorModel":
        """ Creates a flow generator from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        model = GeneratorModel(
            jd["node"], {
                n : [
                    RuleField.from_json(f) for f in fl
                ] for n, fl in list(jd["fields"].items())
            }
        )

        return model


    def port_index(self, port: str) -> int:
        """ Returns an unambigious index of a port of the model.

        Keyword arguments:
        port -- The port's name
        """
        return self.ports[port]


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
