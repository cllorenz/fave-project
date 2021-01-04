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
        self.fields = {
            OXM_FIELD_TO_MATCH_FIELD[name] : [
                SwitchRuleField(
                    OXM_FIELD_TO_MATCH_FIELD[f.name], f.value
                ) for f in field_list
            ] for name, field_list in fields.iteritems()
        } if fields is not None else {}

        self.node = node
        self.type = "generator"
        self.ports = {node+'.1' : 1}


    def to_json(self):
        """ Converts the flow generator to JSON.
        """

        return {
            "fields" : {n:[f.to_json() for f in fl] for n, fl in self.fields.iteritems()},
            "node" : self.node,
            "type" : self.type
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
            j["node"], {
                n : [
                    SwitchRuleField.from_json(f) for f in fl
                ] for n, fl in j["fields"].iteritems()
            }
        )

        return model


    def port_index(self, port):
        """ Returns an unambigious index of a port of the model.

        Keyword arguments:
        port -- The port's name
        """
        return self.ports[port]


    def ingress_port(self, port):
        """ Returns the model's corresponding ingress port.

        Keyword arguments:
        port -- the outer model's port identifier
        """
        return port


    def egress_port(self, port):
        """ Returns the model's corresponding egress port.

        Keyword arguments:
        port -- the outer model's port identifier
        """
        return port
