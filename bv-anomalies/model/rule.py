#!/usr/bin/env python3

import sys

if sys.version_info.major == 3 and sys.version_info.minor >= 6:
    from enum import IntFlag, auto
from enum import IntEnum
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

class Header(IntEnum):
    ipv6_route = 1


class FieldTuple(tuple):
    def __new__(cls, field, negated=False):
        assert(isinstance(field, tuple))
        assert(len(field) == 4)
        _name, _negated, start, end = field
        assert(start <= end)
        return super(FieldTuple, cls).__new__(cls, field)


    field_max = lambda f: {
        'ingress_interface' : 65535,
        'ingress_vlan' : 4095,
        'egress_interface' : 65535,
        'egress_vlan' : 4095,
        'src_ip' : 2**128-1, #2**32-1,
        'dst_ip' : 2**128-1, #2**32-1,
        'proto' : 255,
        'state' : 255,
        'header' : 255,
        'rttype' : 255,
        'rtsegs' : 255,
        'tcp_flags' : 255,
        'src_port' : 65535,
        'dst_port' : 65535
    }[f]


    def subseteq(self, other):
        sname, snegated, sstart, send = self
        oname, onegated, ostart, oend = other

        assert(sname == oname)

        if snegated and onegated:
            return sstart <= ostart and send >= oend
        elif snegated and not onegated:
            raise NotImplementedError() # return ostart == 0 and oend == field_max(sname)
        elif not snegated and onegated:
            return  sstart > oend or send < ostart
        else:
            return sstart >= ostart and send <= oend


    def __str__(self):
        name, negated, start, end = self
        if start == end:
            return "{}={}{}".format(name, "!" if negated else "", start)
        return "{}={}{}..{}".format(name, "!" if negated else "", start, end)


class Match(list):
    def __init__(self, match=None):
        if match:
            assert(isinstance(match, list))
            assert(all([isinstance(f, FieldTuple) for f in match]))
            super(Match, self).__init__(match)

    def add_field_tuple(self, name, start, end, negated=False):
        self.append(FieldTuple((name, negated, start, end)))


    def add_field(self, name, value, negated=False):
        self.add_field_tuple(name, value, value, negated=negated)


    def __str__(self):
        return reduce(lambda x, y: x + ' ' + y, [str(f) for f in self]) if self else ''


class Rule(object):
    def __init__(self, index_, action, match=None, raw="", raw_rule_no=-1):
        assert(isinstance(index_, int))
        assert(hasattr(Action, action))
        self.index = index_
        self.action = action
        self.raw = raw
        self.raw_rule_no = raw_rule_no

        if match:
            assert(isinstance(match, Match))
            self.match = match
        else:
            self.match = Match()


    def __str__(self):
        return "rule {}: {} -> {}".format(self.index, str(self.match), self.action)


    def subseteq(self, other):
        assert(isinstance(other, Rule))

#        print('')
#        print(str(self))
#        print(str(other))

        if not other.match:
#            print("return True due to empty other match")
            return True

        field_name = lambda n, _n, _s, _e: n
        fn = lambda t: field_name(*t)

        self_fields = set([fn(f) for f in self.match])
        other_fields = set([fn(f) for f in other.match])

        if other_fields - self_fields:
#            print("diff:", other_fields - self_fields)
            return False # self match has general fields that are specific in other match

        common_fields = self_fields.intersection(other_fields)

        self_sorted = sorted(self.match, key=fn)
        other_sorted = sorted(other.match, key=fn)

        for self_field, other_field in zip([f for f in self_sorted if fn(f) in common_fields], [f for f in other_sorted if fn(f) in common_fields]):
#            print("try:", self_field, other_field, self_field.subseteq(other_field))
            if not self_field.subseteq(other_field):
#                print("field %s is not subset of %s" % (self_field, other_field))
                return False # self field is more general than or disjunct of other field

        return True
        # ======================= XXX =======================


        sorted_self = sorted(self.match, key=fn)
        sorted_other = sorted(other.match, key=fn)

        print(sorted_self)
        print(sorted_other)

        pre = 0
        while len(sorted_self) < pre and field_name(*sorted_self[pre]) != field_name(*sorted_other[0]):
            pre += 1

        print("pre:", pre)

        cnt = pre
        while len(sorted_self) - pre > cnt and field_name(*sorted_self[cnt]) == field_name(*sorted_other[cnt-pre]):
            if not sorted_self[cnt].subseteq(sorted_other[cnt]):
                print("return False because field %s is not a subset: %s vs. %s" % (fn(sorted_self[cnt]), str(sorted_self[cnt]), str(sorted_other[cnt])))
                return False
            cnt += 1

        print("cnt:", cnt)

        if cnt-pre == len(sorted_other):
            print("return True since other match has been processed completely")
            return True
        else:
            print("return False since there are still specific fields in other match")
            return False
