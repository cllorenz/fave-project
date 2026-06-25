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

""" This module provides models for switch rule fields, matches, actions, and
    switch rules.
"""

from __future__ import annotations

import json

from typing import Any, Dict, Iterable, List, Optional, Union

from util.ip6np_util import field_value_to_bitvector, bitvector_to_field_value
from util.typing_util import JSONDict

from netplumber.vector import Vector, intersect_vectors
from netplumber.mapping import FIELD_SIZES

# A field value: text, a header-space Vector, or None. The None case is real --
# Match.intersect can feed an all-ignore intersection back into a RuleField.
FieldValue = Union[str, "Vector", None]


class RuleField(object):
    """ This class provides a model for switch rules.
    """

    def __init__(
            self, name: str, value: FieldValue, negated: bool = False
    ) -> None:
        self.name = name
        self.value = value
        self.negated = negated


#    # deprecated
#    def vectorize(self):
#        """ Transforms value into a vector representation.
#        """
#
#        if not isinstance(self.value, Vector):
#            self.vector = field_value_to_bitvector(self)


    def to_json(self) -> JSONDict:
        """ Converts the field to JSON.
        """

        return {
            "name" : self.name,
            "value" : self.value,
            "negated" : self.negated
        }


    @staticmethod
    def from_json(j: Union[str, JSONDict]) -> "RuleField":
        """ Creates a switch rule field from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        name = jd["name"]
        value = jd["value"]
        negated = jd["negated"]


        return RuleField(
            name,
            value,
            negated=negated
        )


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RuleField):
            return NotImplemented

        return \
            self.name == other.name and \
            self.value == other.value and \
            self.negated == other.negated


    def intersect(self, other: "RuleField") -> FieldValue:
        """ Intersect field with another of the same type.

        Arguments:
        other -- the other field
        """

        assert isinstance(other, RuleField) and self.name == other.name

        vec1 = field_value_to_bitvector(self).vector
        vec2 = field_value_to_bitvector(other).vector

        return bitvector_to_field_value(intersect_vectors(vec1, vec2), self.name)


class RuleAction(object):
    """ Abstract class for switch rule action models.
    """

    def __init__(self, name: str) -> None:
        self.name = name


    def to_json(self) -> JSONDict:
        """ Converts the action to JSON. Concrete actions override this.
        """
        raise NotImplementedError


    def values_to_vector_str(self) -> None:
        """ Transforms all field values into vector strings.
        """
        pass


class Forward(RuleAction):
    """ This class provides a forward action.
    """

    def __init__(self, ports: Optional[List[str]] = None) -> None:
        super(Forward, self).__init__("forward")
        self.ports: List[str] = ports if ports is not None else []


    def __str__(self) -> str:
        return "forward:[%s]" % ",".join([str(p) for p in self.ports])


    def to_json(self) -> JSONDict:
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name,
            "ports" : self.ports
        }


    @staticmethod
    def from_json(j: Union[str, JSONDict]) -> "Forward":
        """ Constructs a forward action from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """
        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        return Forward(ports=jd["ports"])


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Forward):
            return False

        return self.ports == other.ports


class Rewrite(RuleAction):
    """ This class provides a rewrite action.
    """

    def __init__(self, rewrite: Optional[List[RuleField]] = None) -> None:
        super(Rewrite, self).__init__("rewrite")
        self.rewrite: List[RuleField] = rewrite if rewrite is not None else []


    def __str__(self) -> str:
        return "rewrite:%s" % ",".join(["%s->%s" % (f.name, f.value) for f in self.rewrite])


    def to_json(self) -> JSONDict:
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name,
            "rw" : [field.to_json() for field in self.rewrite],
        }


    @staticmethod
    def from_json(j: Union[str, JSONDict]) -> "Rewrite":
        """ Constructs a rewrite action from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        return Rewrite(
            rewrite=[RuleField.from_json(field) for field in jd["rw"]]
        )


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Rewrite):
            return False

        return len(self.rewrite) == len(other.rewrite) and \
            all([a == b for a, b in zip(self.rewrite, other.rewrite)])


    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class Miss(RuleAction):
    """ This class provides a miss action.
    """

    def __init__(self) -> None:
        super(Miss, self).__init__("miss")


    def __str__(self) -> str:
        return self.name


    def to_json(self) -> JSONDict:
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name
        }


    @staticmethod
    def from_json(_j: object) -> "Miss":
        """ Constructs a miss action from JSON.
        """
        return Miss()


    def __eq__(self, other: object) -> bool:
        return isinstance(other, Miss)


class Match(List[RuleField]):
    """ This class provides models for switch rule matches.
    """

    def __init__(self, fields: Optional[Iterable[RuleField]] = None) -> None:
        super(Match, self).__init__(fields if fields is not None else [])


    def to_json(self) -> JSONDict:
        """ Converts the match to JSON.
        """

        return {
            "fields" : [field.to_json() for field in self],
        }


    def __str__(self) -> str:
        return ",".join(["%s=%s" % (f.name, f.value) for f in self])


    @staticmethod
    def from_json(j: Union[str, JSONDict, None]) -> "Match":
        """ Construct a match from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if not j:
            return Match()

        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        return Match(
            fields=[RuleField.from_json(f) for f in jd["fields"]]
        )


    def filter(self, field: Union[RuleField, str]) -> None:
        """ Remove field from match if present.

        Arguments:
        field -- the field or field name to remove
        """

        if isinstance(field, RuleField):
            name = field.name
        elif isinstance(field, str):
            name = field
        else:
            raise Exception("cannot filter match for a field of type: %s" % type(field))

        for fld in self:
            if fld.name == name:
                self.remove(fld)


    def get(self, field: str) -> RuleField:
        """ Get field from match.

        Arguments:
        field -- the field name
        """

        assert isinstance(field, str)

        for fld in self:
            if fld.name == field:
                return fld
        raise Exception("no such field: %s" % field)


    def intersect(self, other: "Match") -> "Match":
        """ Intersect match with another.

        Arguments:
        other -- the other match
        """

        if not self:
            return Match(other)
        elif not other:
            return Match(self)

        isect = []
        idx1 = idx2 = 0

        match1 = sorted(self, key=lambda f: f.name)
        match2 = sorted(other, key=lambda f: f.name)

        while idx1 < len(match1) and match1[idx1].name != match2[idx2].name:
            isect.append(match1[idx1])
            idx1 += 1

        while idx1 < len(match1) and idx2 < len(match2):
            field1 = match1[idx1]
            field2 = match2[idx2]
            if field1.name == field2.name and field1.name not in ['in_port', 'out_port']:
                isect.append(RuleField(field1.name, field1.intersect(field2)))
                idx1 += 1
                idx2 += 1
            elif field1.name == field2.name:
                if field1.value == field2.value:
                    isect.append(RuleField(field1.name, field1.value))

                idx1 += 1
                idx2 += 1
            else:
                break

        if idx1 < len(match1):
            isect.extend(match1[idx1:])
        if idx2 < len(match2):
            isect.extend(match2[idx2:])

        return Match(isect)


class Rule(object):
    """ This class provides a model for switch rules.
    """

    def __init__(
            self,
            node: str,
            tid: Union[int, str],
            idx: int,
            in_ports: Optional[List[str]] = None,
            match: Optional[Match] = None,
            actions: Optional[List[RuleAction]] = None,
            raw_line_no: Optional[int] = None,
            raw_line: Optional[str] = None
    ) -> None:
        self.node = node
        self.mtype = "switch_rule"
        self.tid = tid
        self.idx = idx
        self.in_ports: List[str] = in_ports if in_ports is not None else []
        self.match: Match = match if match else Match()
        self.actions: List[RuleAction] = actions if actions is not None else []
        self.raw_line_no = raw_line_no
        self.raw_line = raw_line


    def __hash__(self) -> int:
        return hash(
            "%s.%s" % (self.tid, self.idx) +
            str(self.match) +
            ",".join(str(a) for a in self.actions)
        )


    def to_json(self) -> JSONDict:
        """ Converts the rule to JSON.
        """
        return {
            "node" : self.node,
            "tid" : self.tid,
            "idx" : self.idx,
            "in_ports" : self.in_ports,
            "match" : self.match.to_json() if self.match else None,
            "actions" : [action.to_json() for action in self.actions],
            "raw_line_no" : self.raw_line_no,
            "raw_line" : self.raw_line
        }


    @staticmethod
    def from_json(j: Union[str, JSONDict]) -> "Rule":
        """ Constructs a switch rule from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        # name -> action class; heterogeneous, hence Any.
        actions: Dict[str, Any] = {
            "forward" : Forward,
            "rewrite" : Rewrite,
            "miss" : Miss
        }

        return Rule(
            node=jd["node"],
            tid=int(jd["tid"]) if isinstance(jd["tid"], str) and jd["tid"].isdigit() else jd["tid"],
            idx=int(jd["idx"]),
            in_ports=jd["in_ports"],
            match=Match.from_json(jd["match"]),
            actions=[actions[action["name"]].from_json(action) for action in jd["actions"]],
            raw_line_no=jd["raw_line_no"],
            raw_line=jd["raw_line"]
        )

    def __str__(self) -> str:
        return "%s\nnode:%s\ntid: %s\nidx: %s\nmatch:\n\t%s\nactions:\n\t%s\n" % (
            self.mtype,
            self.node,
            self.tid,
            self.idx,
            self.match,
            self.actions
        )


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Rule):
            return NotImplemented

        return all([
            self.node == other.node,
            self.tid == other.tid,
            self.idx == other.idx,
            self.in_ports == other.in_ports,
            self.match == other.match,
            self.actions == other.actions,
            self.raw_line_no == other.raw_line_no,
            self.raw_line == other.raw_line
        ])


    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result
