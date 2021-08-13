#!/usr/bin/env python2

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

""" This module provides models for switch rule fields, matches, actions, and
    switch rules.
"""

import sys
import getopt
import json

try:
    from ip6np.ip6np_util import field_value_to_bitvector, bitvector_to_field_value, VectorConstructionError
except ImportError:
    from ip6np_util import field_value_to_bitvector, bitvector_to_field_value, VectorConstructionError

from netplumber.vector import Vector, set_field_in_vector, intersect_vectors
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.model import Model


class SwitchRuleField(object):
    """ This class provides a model for switch rules.
    """

    def __init__(self, name, value, negated=False):
        self.name = name
        self.value = value
        self.negated = negated


    def vectorize(self):
        """ Transforms value into a vector representation.
        """

        if not isinstance(self.value, Vector):
            self.vector = field_value_to_bitvector(self)


    def to_json(self):
        """ Converts the field to JSON.
        """

        return {
            "name" : self.name,
            "value" : self.value.vector if isinstance(self.value, Vector) else self.value,
            "negated" : self.negated
        }


    @staticmethod
    def from_json(j):
        """ Creates a switch rule field from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        name = j["name"]
        value = j["value"]
        negated = j["negated"]

        if Vector.is_vector(value, name=name):
            value = Vector.from_vector_str(value)
            assert value.length == FIELD_SIZES[name]


        return SwitchRuleField(
            name,
            value,
            negated=negated
        )


    def __eq__(self, other):
        if other == None: return False
        assert isinstance(other, SwitchRuleField)

        return self.name == other.name and self.value == other.value and self.negated == other.negated


    def intersect(self, other):
        assert isinstance(other, SwitchRuleField) and self.name == other.name

        v1 = field_value_to_bitvector(self).vector
        v2 = field_value_to_bitvector(other).vector

        return bitvector_to_field_value(intersect_vectors(v1, v2), self.name)


class SwitchRuleAction(object):
    """ Abstract class for switch rule action models.
    """

    def __init__(self, name):
        self.name = name


    def values_to_vector_str(self):
        """ Transforms all field values into vector strings.
        """
        pass


class Forward(SwitchRuleAction):
    """ This class provides a forward action.
    """

    def __init__(self, ports=None):
        super(Forward, self).__init__("forward")
        self.ports = ports if ports is not None else []


    def __str__(self):
        return "forward:[%s]" % ",".join([str(p) for p in self.ports])


    def to_json(self):
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name,
            "ports" : self.ports
        }


    @staticmethod
    def from_json(j):
        """ Constructs a forward action from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """
        if isinstance(j, str):
            j = json.loads(j)

        return Forward(ports=j["ports"])


    def __eq__(self, other):
        if not isinstance(other, Forward):
            return False

        return self.ports == other.ports


class Rewrite(SwitchRuleAction):
    """ This class provides a rewrite action.
    """

    def __init__(self, rewrite=None):
        super(Rewrite, self).__init__("rewrite")
        self.rewrite = rewrite if rewrite is not None else [] # type: [Field()]


    def __str__(self):
        return "rewrite:%s" % ",".join(["%s->%s" % (f.name, f.value) for f in self.rewrite])


    def to_json(self):
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name,
            "rw" : [field.to_json() for field in self.rewrite],
        }


    @staticmethod
    def from_json(j):
        """ Constructs a rewrite action from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return Rewrite(
            rewrite=[SwitchRuleField.from_json(field) for field in j["rw"]]
        )


    def __eq__(self, other):
        if not isinstance(other, Rewrite):
            return False

        return len(self.rewrite) == len(other.rewrite) or \
            all([a == b for a, b in zip(self.rewrite, other.rewrite)])


class Miss(SwitchRuleAction):
    """ This class provides a miss action.
    """

    def __init__(self):
        super(Miss, self).__init__("miss")


    def __str__(self):
        return self.name


    def to_json(self):
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name
        }


    @staticmethod
    def from_json(_j):
        """ Constructs a miss action from JSON.
        """
        return Miss()


    def __eq__(self, other):
        return isinstance(other, Miss)


class Match(list):
    """ This class provides models for switch rule matches.
    """

    def __init__(self, fields=None):
        super(Match, self).__init__(fields if fields is not None else [])


    def to_json(self):
        """ Converts the match to JSON.
        """

        return {
            "fields" : [field.to_json() for field in self],
        }


    def __str__(self):
        return ",".join(["%s=%s" % (f.name, f.value) for f in self])


    @staticmethod
    def from_json(j):
        """ Construct a match from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if not j:
            return Match()

        if isinstance(j, str):
            j = json.loads(j)

        return Match(
            fields=[SwitchRuleField.from_json(f) for f in j["fields"]]
        )


    def filter(self, field):
        if isinstance(field, SwitchRuleField):
            name = field.name
        elif isinstance(field, str):
            name = field
        else:
            raise Exception("cannot filter match for a field of type: %s" % type(field))

        for f in self:
            if f.name == name:
                self.remove(f)


    def get(self, field):
        assert isinstance(field, str)

        for f in self:
            if f.name == field:
                return f
        raise Exception("no such field: %s" % field)


    def intersect(self, other):
        if len(self) == 0:
            return Match(other)
        elif len(other) == 0:
            return Match(self)

        isect = []
        idx1 = idx2 = 0

        match1 = sorted(self, key=lambda f: f.name)
        match2 = sorted(self, key=lambda f: f.name)

        while match1[idx1].name != match2[idx2].name and idx1 < len(match1):
            isect.append(match1[idx1])
            idx1 += 1

        while idx1 < len(match1) and idx2 < len(match2):
            field1 = match1[idx1]
            field2 = match2[idx2]
            if field1.name == field2.name and field1.name not in ['in_port', 'out_port']:
                isect.append(SwitchRuleField(field1.name, field1.intersect(field2)))
                idx1 += 1
                idx2 += 1
            elif field1.name == field2.name:
                if field1.value == field2.value:
                    isect.append(SwitchRuleField(field1.name, field1.value))

                idx1 += 1
                idx2 += 1
            else:
                break

        if idx1 < len(match1):
            isect.extend(match1[idx1:])
        if idx2 < len(match2):
            isect.extend(match2[idx2:])

        return Match(isect)


class SwitchRule(Model):
    """ This class provides a model for switch rules.
    """

    def __init__(self, node, tid, idx, in_ports=None, match=None, actions=None):
        super(SwitchRule, self).__init__(node, mtype="switch_rule")
        self.tid = tid
        self.idx = idx
        self.in_ports = in_ports if in_ports is not None else []
        self.match = match if match else Match()
        self.actions = actions if actions is not None else []


    def __hash__(self):
        return hash(
            "%s.%s" % (self.tid, self.idx) +
            str(self.match) +
            ",".join(str(a) for a in self.actions)
        )


    def to_json(self):
        """ Converts the rule to JSON.
        """
        return {
            "node" : self.node,
            "tid" : self.tid,
            "idx" : self.idx,
            "in_ports" : self.in_ports,
            "match" : self.match.to_json() if self.match else None,
            "actions" : [action.to_json() for action in self.actions]
        }


    @staticmethod
    def from_json(j):
        """ Constructs a switch rule from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        actions = {
            "forward" : Forward,
            "rewrite" : Rewrite,
            "miss" : Miss
        }

        return SwitchRule(
            node=j["node"],
            tid=int(j["tid"]) if isinstance(j["tid"], str) and j["tid"].isdigit() else j["tid"],
            idx=int(j["idx"]),
            in_ports=j["in_ports"],
            match=Match.from_json(j["match"]),
            actions=[actions[action["name"]].from_json(action) for action in j["actions"]]
        )

    def __str__(self):
        return "%s\ntid: %s\nidx: %s\nmatch:\n\t%s\nactions:\n\t%s\n" % (
            super(SwitchRule, self).__str__(),
            self.tid,
            self.idx,
            self.match,
            self.actions
        )


    def __eq__(self, other):
        assert isinstance(other, SwitchRule)

        return all([
            self.node == other.node,
            self.tid == other.tid,
            self.idx == other.idx,
            self.in_ports == other.in_ports,
            self.match == other.match,
            self.actions == other.actions
        ])


    def __ne__(self, other):
        assert isinstance(other, SwitchRule)
        return not self == other
