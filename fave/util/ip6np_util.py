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

""" This module provides utilities for packet filter models.
"""

from util.packet_util import normalize_vlan_tag
from util.packet_util import normalize_ipv4_address
from util.packet_util import normalize_ipv6_address, normalize_upper_port
from util.packet_util import normalize_ipv6_proto, normalize_ipv6header_header
from util.packet_util import denormalize_ipv4_address, denormalize_ipv6_address

from netplumber.mapping import FIELD_SIZES
from netplumber.vector import Vector


class FieldNotImplementedError(Exception):
    """ This exception indicates a missing implementation for a field.
    """

    def __init__(self, name):
        super(FieldNotImplementedError, self).__init__()
        self.name = name


    def __str__(self):
        return "Field %s is not implemented." % self.name


class VectorConstructionError(Exception):
    """ This exception indicates that no vector could be constructed for a field's value.
    """

    def __init__(self, name, value):
        super(VectorConstructionError, self).__init__()
        self.name = name
        self.value = value


    def __str__(self):
        return "Could not construct vector for field %s from %s" % (self.name, self.value)


def _normalize_interface(interface):
    return '{:032b}'.format(int(interface)) if interface != 'lo' else '0'*32


def _normalize_module(module):
    return {
        "ipv6header" : "00000001",
        "limit" : "00000010",
        "state" : "00000011",
        "rt" : "00000100",
        "ah" : "00000101",
        "dst" : "00000110",
        "eui64" : "00000111",
        "frag" : "00001000",
        "hbh" : "00001001",
        "hl" : "00001010",
        "icmpv6" : "00001011",
        "mh" : "00001100",
        "tos" : "00001101",
        "tcp" : "xxxxxxxx",
        "udp" : "xxxxxxxx"
    }[module]


def _normalize_limit(limit):
    # fields have the format value/unit
    val, unit = limit.split("/")
    factor = {
        None : 3600,
        "sec" : 1,
        "min" : 60,
        "hour" : 3600,
        "day" : 86400
    }[unit]
    return "{0:032b}".format(int(val) * factor)


def _normalize_states(states):
    states = states.split(",") if "," in states else [states]
    to_bit = lambda x: {"NEW":1, "RELATED":2, "ESTABLISHED":4, "INVALID":8}[x]
    bitmap = reduce(lambda x, y: x|y, [to_bit(x) for x in states])
    return "{0:08b}".format(bitmap)


def _normalize_icmpv6_type(icmpv6_type):
    return {
        "destination-unreachable" : "00000001xxxxxxxx",
        "packet-too-big" : "00000010xxxxxxxx",
        "time-exceeded" : "00000011xxxxxxxx",
        "parameter-problem" : "00000100xxxxxxxx",
        "echo-request" : "10000000xxxxxxxx",
        "echo-reply" : "10000001xxxxxxxx",
        "neighbour-solicitation" : "10000111xxxxxxxx",
        "neighbour-advertisement" : "10001000xxxxxxxx",
        "ttl-zero-during-transit" : "0000001100000000",
        "unknown-header-type" : "0000010000000001",
        "unknown-option" : "0000010000000010",
    }[icmpv6_type]


# TODO: implement ranges
def _normalize_rt_type(rt_type):
    try:
        lrt, rrt = rt_type.split(':')
        return lrt, rrt
    except ValueError:
        return "{0:08b}".format(int(rt_type))
    else:
        raise Exception("Range not implemented on field: rt_type")


def _normalize_ipv6header(header):
    return "{0:08b}".format(int(header))


def _normalize_frag_id(frag_id):
    return "{0:032b}".format(frag_id)

# TODO: implement ranges
def _normalize_ah_spi(ah_spi):
    try:
        lspi, rspi = ah_spi.split(':')
        return lspi, rspi
    except ValueError:
        return "{0:032b}".format(int(ah_spi))
    else:
        raise Exception("Range not implemented on field: ah.spi")


def _normalize_ah_res(ah_res):
    return "{0:016b}".format(int(ah_res))


def _normalize_mh_type(mh_type):
    return "{0:08b}".format(int(mh_type))


def _normalize_related(bit):
    return "%sxxxxxxx" % bit


def _try_int(val):
    try:
        int(val)
    except ValueError:
        return False
    return True

# XXX: refactor and move to own utility module
def field_value_to_bitvector(field):
    """ Converts field value to its bitvector representation.

    Keyword arguments:
    field -- a header field
    """

    name = field.name
    size = FIELD_SIZES[name]
    value = field.value

    if isinstance(value, Vector):
        return value
    elif Vector.is_vector(str(value), name=name):
        vec = Vector(length=size)
        vec[:] = value
        return vec
    elif _try_int(value):
        vec = Vector(length=size)
        vec[:] = ('{0:0%sb}' % size).format(int(value))
        return vec

    vector = Vector(length=size)
    try:
        vector[:] = {
            "related" : _normalize_related,
            "packet.ether.vlan" : normalize_vlan_tag,
            "packet.ether.svlan" : normalize_vlan_tag,
            "packet.ether.dvlan" : normalize_vlan_tag,
            "packet.ipv4.source" : normalize_ipv4_address,
            "packet.ipv4.destination" : normalize_ipv4_address,
            "packet.ipv6.source" : normalize_ipv6_address,
            "packet.ipv6.destination" : normalize_ipv6_address,
            "packet.upper.sport" : normalize_upper_port,
            "packet.upper.dport" : normalize_upper_port,
            "interface" : _normalize_interface,
            "in_port" : _normalize_interface,
            "out_port" : _normalize_interface,
            "module" : _normalize_module,
            "module.ipv6header.header" : normalize_ipv6header_header,
            "module.limit" : _normalize_limit,
            "module.state" : _normalize_states,
            "module.conntrack.ctstate" : _normalize_states,
            "packet.ipv6.proto" : normalize_ipv6_proto,
            "packet.ipv6.icmpv6.type" : _normalize_icmpv6_type,
            "module.ipv6header.rt.len" : _normalize_ipv6header,
            "module.ipv6header.rt.segsleft" : _normalize_ipv6header,
            "module.ipv6header.ah.len" : _normalize_ipv6header,
            "module.ipv6header.dst.len" : _normalize_ipv6header,
            "module.ipv6header.frag.len" : _normalize_ipv6header,
            "module.ipv6header.hbh.len" : _normalize_ipv6header,
            "module.ipv6header.hl.eq" : _normalize_ipv6header,
            "module.ipv6header.rt.type" : _normalize_rt_type,
            "module.ipv6header.frag.id" : _normalize_frag_id,
            "module.ipv6header.ah.res" : _normalize_ah_res,
            "module.ipv6header.ah.spi" : _normalize_ah_spi,
            "module.ipv6header.mh.type" : _normalize_mh_type
        }[name](value)

    except ValueError:
        if Vector.is_vector(value):
            vector = Vector.from_vector_str(value)
        else:
            raise VectorConstructionError(name, value)

    except KeyError:
        raise FieldNotImplementedError(name)

    return vector


def bitvector_to_field_value(vector, field, ignore_bit='x', printable=False):
    assert len(vector) == FIELD_SIZES[field]

    if (ignore_bit * FIELD_SIZES[field] == vector):
        return None

    try:
        return {
            "packet.ipv4.source" : denormalize_ipv4_address,
            "packet.ipv4.destination" : denormalize_ipv4_address,
            "packet.ipv6.source" : denormalize_ipv6_address,
            "packet.ipv6.destination" : denormalize_ipv6_address
        }[field](vector)
    except KeyError:
        pass

    if all([bit in ['0', '1'] for bit in vector]):
        if printable and field in ['interface', 'in_port', 'out_port']:
            return hex(int(vector, 2))
        else:
            return str(int(vector, 2))
    else:
        return None
