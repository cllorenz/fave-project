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

import json
import itertools

from netplumber.mapping import Mapping
from netplumber.vector import set_field_in_vector, Vector, HeaderSpace
from ip6np.ip6np_util import field_value_to_bitvector
from openflow.switch import SwitchRuleField
from util.match_util import OXM_FIELD_TO_MATCH_FIELD

class GeneratorModel(object):
    """ This class provides a flow generator model.
    """

    def __init__(self, node, fields=None):
        fields = fields if fields is not None else {}

        self.node = node
        self.type = "generator"
        self.ports = {node+'_1' : 1}

        self.mapping = Mapping()

        for field in fields:
            self.mapping.extend(OXM_FIELD_TO_MATCH_FIELD[field])

        outgoing = []

        keys = sorted(fields)
        combinations = itertools.product(*(fields[k] for k in keys))

        for comb in combinations:
            vector = Vector(self.mapping.length)
            for i, oxm in enumerate(keys):
                field = OXM_FIELD_TO_MATCH_FIELD[oxm]
                set_field_in_vector(
                    self.mapping,
                    vector,
                    field,
                    field_value_to_bitvector(
                        SwitchRuleField(field, comb[i])
                    ).vector
                )
            outgoing.append(vector)

        self.outgoing = HeaderSpace(self.mapping.length, outgoing)


    def to_json(self):
        """ Converts the flow generator to JSON.
        """

        return {
            "node" : self.node,
            "type" : self.type,
            "mapping" : self.mapping.to_json(),
            "outgoing" : self.outgoing.to_json()
        }

    @staticmethod
    def from_json(j):
        """ Creates a flow generator from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        model = GeneratorModel(
            j["node"],
        )
        model.mapping = Mapping.from_json(j["mapping"])
        model.outgoing = HeaderSpace.from_json(j["outgoing"])

        return model
