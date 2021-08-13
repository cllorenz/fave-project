""" This module provides a probe model.
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

from util.path_util import Path
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from netplumber.mapping import Mapping
from netplumber.vector import set_field_in_vector, Vector, HeaderSpace
from ip6np.ip6np_util import field_value_to_bitvector
from openflow.rule import SwitchRuleField, Match

class ProbeModel(object):
    """ This class provides a probe model.
    """

    @staticmethod
    def _normalize_fields(fields):
        return {
            OXM_FIELD_TO_MATCH_FIELD[name] : [
                SwitchRuleField(
                    OXM_FIELD_TO_MATCH_FIELD[f.name], f.value
                ) for f in field_list
            ] for name, field_list in fields.iteritems()
        }


    def __init__(self, node, quantor, match=None, filter_fields=None, filter_path=None, test_fields=None, test_path=None):
        self.node = node
        self.type = "probe"
        self.ports = {node+'.1' : 1}
        self.quantor = quantor
        self.match = match if match is not None else Match([])

        self.filter_fields = ProbeModel._normalize_fields(filter_fields)
        self.test_fields = ProbeModel._normalize_fields(test_fields)

        if filter_path is not None and isinstance(filter_path, Path):
            self.filter_path = filter_path
        elif filter_path is not None:
            self.filter_path = Path(filter_path)
        else:
            self.filter_path = Path()

        if test_path is not None and isinstance(test_path, Path):
            self.test_path = test_path
        elif test_path is not None:
            self.test_path = Path(test_path)
        else:
            self.test_path = Path()


    def to_json(self):
        """ Converts the probe to JSON.
        """

        return {
            "node" : self.node,
            "type" : self.type,
            "quantor" : self.quantor,
            "match" : self.match.to_json(),
            "filter_fields" : {n : [f.to_json() for f in fl] for n, fl in self.filter_fields.iteritems()},
            "filter_path" : self.filter_path.to_json(),
            "test_fields" : {n : [f.to_json() for f in fl] for n, fl in self.test_fields.iteritems()},
            "test_path" : self.test_path.to_json()
        }

    @staticmethod
    def from_json(j):
        """ Creates a probe from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        model = ProbeModel(
            j["node"],
            j["quantor"],
            Match.from_json(j["match"]),
            filter_fields={n : [SwitchRuleField.from_json(f) for f in fl] for n, fl in j['filter_fields'].iteritems()},
            filter_path=Path.from_json(j["filter_path"]),
            test_fields={n : [SwitchRuleField.from_json(f) for f in fl] for n, fl in j['test_fields'].iteritems()},
            test_path=Path.from_json(j["test_path"])
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
