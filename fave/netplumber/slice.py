#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2019 Jan Sohre

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

""" This module provides classes to store and exchange slice models and slice
    commands.
"""

import json

from netplumber.mapping import Mapping


class Slice(object):
    """ This class represents a slice model.
    """

    def __init__(self, sid, ns_list=None, ns_diff=None):
        self.sid = sid
        self.ns_list = ns_list if ns_list else []
        self.ns_diff = ns_diff if ns_diff else []


    def to_json(self):
        """ Convert the slice to a json representation.
        """

        return {
            "sid" : self.sid,
            "ns_list" : self.ns_list,
            "ns_diff" : self.ns_diff
        }


    @staticmethod
    def from_json(j):
        """ Retrieve a slice from its json representation.
        """

        if isinstance(j, str):
            j = json.loads(j)

        return Slice(
            j["sid"], ns_list=j["ns_list"], ns_diff=j["ns_list"]
        )


class SlicingCommand(object):
    """ This class represents a slicing command.
    """

    def __init__(self, command, mapping=None, slicem=None):
        assert command in ['add_slice', 'del_slice']

        self.command = command

        self.mapping = mapping if mapping else Mapping(0)
        assert isinstance(self.mapping, Mapping)

        self.slice = slicem if slicem else Slice(0)
        assert isinstance(self.slice, Slice)

        for fld, _val in self.slice.ns_list:
            self.mapping.extend(fld)
        for fld, _val in self.slice.ns_diff:
            self.mapping.extend(fld)


    def to_json(self):
        """ Convert a slice command to its json representation.
        """

        return {
            "command" : self.command,
            "mapping" : self.mapping.to_json(),
            "slice" : self.slice.to_json()
        }


    @staticmethod
    def from_json(j):
        """ Retrieve a slice command from its json representation.
        """

        if isinstance(j, str):
            j = json.loads(j)

        return SlicingCommand(
            j["command"],
            mapping=Mapping.from_json(j["mapping"]),
            slicem=Slice.from_json(j["slice"])
        )
