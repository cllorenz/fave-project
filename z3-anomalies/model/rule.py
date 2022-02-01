#!/usr/bin/env python3

import sys

if sys.version_info.major == 3 and sys.version_info.minor >= 6:
    from enum import IntFlag, auto
from enum import IntEnum
from z3 import Int, And
from functools import reduce


Action = IntEnum('action', 'accept drop')
State = IntEnum('state', 'NEW ESTABLISHED')

class Proto(IntEnum):
    icmp = 1
    icmpv6 = 58
    tcp = 6
    udp = 17
    esp = 50
    gre = 47

if sys.version_info.major == 3 and sys.version_info.minor >= 6:
    class Flag(IntFlag):
        SYN = auto()
        ACK = auto()
        FIN = auto()

else:
    class Flag(IntEnum):
        SYN = 1
        ACK = 2
        FIN = 4


class FieldTuple(tuple):
    def __new__(cls, field):
        assert(isinstance(field, tuple))
        assert(len(field) == 3)
        name, start, end = field
        assert(start <= end)
        return super(FieldTuple, cls).__new__(cls, field)


    def to_z3(self):
        name, start, end = self
        var = Int(name)
        if start == end:
            return (var == start)
        return And(var >= start, var <= end)


    def __str__(self):
        name, start, end = self
        if start == end:
            return "{}={}".format(name, start)
        return "{}={}..{}".format(name, start, end)


class Match(list):
    def __init__(self, match=None):
        if match:
            assert(isinstance(match, list))
            assert(all([isinstance(f, FieldTuple) for f in match]))
            super(Match, self).__init__(match)

    def add_field_tuple(self, name, start, end):
        self.append(FieldTuple((name, start, end)))


    def add_field(self, name, value):
        self.add_field_tuple(name, value, value)


    def __str__(self):
        return reduce(lambda x, y: x + ' ' + y, [str(f) for f in self])


class Rule(object):
    def __init__(self, index_, action, match=None, raw="", raw_rule_no=-1):
        assert(isinstance(index_, int))
        assert(hasattr(Action, action))
        self.index = index_
        self.action = action
        self.z3_cache = None
        self.raw = raw
        self.raw_rule_no = raw_rule_no

        if match:
            assert(isinstance(match, Match))
            self.match = match
        else:
            self.match = Match()


    def __str__(self):
        return "rule {}: {} -> {}".format(self.index, str(self.match), self.action)


    def to_z3(self):
        if self.z3_cache is not None: return self.z3_cache

        z3_fields = [f.to_z3() for f in self.match]

        z3_rule = And(*z3_fields)
        self.z3_cache = z3_rule

        return z3_rule
