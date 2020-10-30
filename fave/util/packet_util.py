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

""" This module provides packet constants and utilities.
"""

import re

ETHER_TYPE_IPV4 = '00000100' # 4
ETHER_TYPE_IPV6 = '00000110' # 6

IP_PROTO_ICMP = '00000001'   # 1
IP_PROTO_ICMPV6 = '00111010' # 58
IP_PROTO_TCP = '00000110'    # 6
IP_PROTO_UDP = '00010001'    # 17
IP_PROTO_ESP = '00110010'    # 50
IP_PROTO_GRE = '00101111'    # 47

IPV6_ROUTE = '00101011'      # 43
IPV6_HOP = '00000000'        # 0
IPV6_HBH = '00000000'        # 0
IPV6_DST = '00111100'        # 60
IPV6_FRAG = '00101100'       # 44
IPV6_AUTH = '00110011'       # 51
IPV6_ESP = '00110010'        # 50
IPV6_NONE = '00111011'       # 59
IPV6_PROT = '11111111'       # 255


def is_ip(ips):
    """ Checks if a string represents a valid IPv4 CIDR.

    Keyword arguments:
    ips -- a string
    """
    try:
        ips, cidr = ips.split("/")
        i = int(cidr)
        if i < 0 or i > 32:
            return False
    except ValueError:
        pass

    elems = ips.split(".")
    if len(elems) != 4:
        return False
    try:
        for elem in elems:
            i = int(elem)
            if i < 0 or i > 255:
                return False
    except ValueError:
        return False

    return True


def is_domain(domains):
    """ Checks if a string is a valid domain name.

    Keyword arguments:
    domains -- a string
    """
    labels = domains.split(".")
    label = re.compile("^[a-zA-Z](([-a-zA-Z0-9]+)?[a-zA-Z0-9])?$") # cf. RFC1025
    return all([re.match(label, l) for l in labels])


def is_unix(unixs):
    """ Checks if a string is a valid unix domain socket address.

    Keyword arguments:
    unixs -- a string
    """
    return '\0' not in unixs


def is_port(ports):
    """ Checks if a string is a valid port number.

    Keyword arguments:
    ports -- a string
    """
    try:
        port = int(ports)
        return port >= 0 and port <= 0xffff
    except ValueError:
        return False

    return False


def is_ext_port(ports):
    """ Checks if a string is a valid interface number.

    Keyword arguments:
    ports -- a string
    """
    return is_port(ports)


def normalize_vlan_tag(vlan):
    """ Normalizes vlan tags.

    Keyword arguments:
    vlan -- a vlan tag
    """

    vlan_tag = int(vlan)
    assert vlan_tag >= 0 and vlan_tag < 4096

    return '{:016b}'.format(vlan_tag) if vlan_tag != 0 else 'x'*16


def normalize_upper_port(port):
    """ Normalizes upper protocol port numbers.

    Keyword arguments:
    port -- a port number
    """

    portno = int(port)
    assert portno > 0 and portno < 65536

    return '{:016b}'.format(portno)


def normalize_ipv4_address(address):
    """ Normalizes an IPv4 address.

    Keyword arguments:
    address -- an IPv4 address in dotted or cidr notation
    """

    match = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$", address)
    if not match:
        raise ValueError("%s is not an ipv4 address" % address)

    try:
        addr, cidr = address.split('/')
    except ValueError:
        addr = address
        cidr = None

    addr = ''.join(["{:08b}".format(int(x)) for x in addr.split('.')])

    if cidr and int(cidr) < 32:
        cidr = int(cidr)
        addr = addr[:cidr] + 'x'*(32-cidr)

    return addr


def normalize_ipv6_address(address):
    """ Normalizes an IPv6 address.

    Keyword arguments:
    address -- an IPv6 address in full, cidr, or short notation
    """

    try:
        addr, cidr = address.split("/")
    except ValueError:
        addr = address
        cidr = None

    try:
        laddr, raddr = addr.split("::")
    except ValueError:
        laddr = addr
        raddr = ''

    if laddr:
        laddr = laddr.split(":")
    else:
        laddr = []

    if raddr:
        raddr = raddr.split(":")
    else:
        raddr = []

    laddr += ["0"] * (8-len(laddr)-len(raddr)) + raddr
    addr = "".join(["{:016b}".format(int(block, 16)) for block in laddr])

    if cidr and int(cidr) < 128:
        cidr = int(cidr)
        addr = addr[:cidr] + 'x'*(128-cidr)

    return addr


def normalize_ipv6_proto(proto):
    """ Normalizes the IPv6 upper protocol field (last next header field in chain).

    Keyword arguments:
    proto -- the protocol field value
    """
    return {
        "gre"       : IP_PROTO_GRE,
        "esp"       : IP_PROTO_ESP,
        "icmp"      : IP_PROTO_ICMP,
        "icmpv6"    : IP_PROTO_ICMPV6,
        "tcp"       : IP_PROTO_TCP,
        "udp"       : IP_PROTO_UDP,
    }[proto]


def normalize_ipv6header_header(header):
    """ Normalizes the IPv6 next header field.

    Keyword arguments:
    header -- the next header field value
    """

    return {
        "ipv6-route"    : IPV6_ROUTE,
        "hop"           : IPV6_HOP,
        "hop-by-hop"    : IPV6_HBH,
        "dst"           : IPV6_DST,
        "route"         : IPV6_ROUTE,
        "frag"          : IPV6_FRAG,
        "auth"          : IPV6_AUTH,
        "esp"           : IPV6_ESP,
        "none"          : IPV6_NONE,
        "prot"          : IPV6_PROT
    }[header]



def _denormalize_ip_address(vector, alen, blen, bform, delim):
    baddr = ""
    for bit in vector:
        if bit == 'x':
            break
        baddr += bit

    cidr = len(baddr)

    if not all([bit == 'x' for bit in vector[cidr:]]):
        return vector

    if cidr < alen:
        baddr += '0'*(alen-cidr)

    res = []
    for i in range(0, alen, blen):
        res.append(bform(int(baddr[i:i+blen], 2)))

    return delim.join(res) + (("/%s"%cidr) if cidr != alen else "")


def denormalize_ipv4_address(vector):
    """ Converts a ternary bit vector to an IPv4 prefix representation

    Keyword arguments:
    vector - the ternary bit vector representing the IPv4 prefix
    """
    assert len(vector) == 32
    return _denormalize_ip_address(vector, 32, 8, str, '.')


def denormalize_ipv6_address(vector):
    """ Converts a ternary bit vector to an IPv6 prefix representation

    Keyword arguments:
    vector - the ternary bit vector representing the IPv6 prefix
    """
    assert len(vector) == 128
    return _denormalize_ip_address(vector, 128, 16, lambda x: hex(x)[2:], ':')


PORT_BITS = 16
def portrange_to_prefix_list(lower, upper):
    """ Converts a range of ports to a list of prefixes.

    Keyword arguments:
    lower - the lowest port
    upper - the highest port
    """
    assert all([lower >= 0, lower <= 65535, upper >= 0, upper <= 65535, lower <= upper])

    res = []

    if lower == upper:
        return [(lower, PORT_BITS)]

    while lower < upper:
        postfix = 0
        for postfix in range(PORT_BITS):
            if (lower % (1 << (postfix + 1)) != 0) or (lower + (1 << (postfix + 1)) - 1 > upper):
                break

        res.append((lower, PORT_BITS - postfix))
        lower += (1 << postfix)

    return res


def portrange_to_prefixed_bitvectors(lower, upper):
    prefixes = portrange_to_prefix_list(lower, upper)

    res = []
    for base, prefix in prefixes:
        res.append("{:016b}".format(base)[:prefix] + "x" * (PORT_BITS - prefix))

    return res
