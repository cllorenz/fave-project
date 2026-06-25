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

from __future__ import annotations

import re
import ipaddress

from typing import Any, Callable, List, Optional, Tuple

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


# --- canonicalization --------------------------------------------------------
#
# A field value can be written several equivalent ways: an IPv6 address has many
# syntaxes (2001:db8::1 == 2001:db8:0:0:0:0:0:1), a CIDR can be compact or
# expanded, and a protocol can be given by name or IANA number (tcp == 6).
# These collapse to one bit-vector downstream, but model *equality* (the
# aggregator's incremental diff) compares the raw value strings -- so two
# equivalent rules written differently would be treated as different rules.
# canonicalize_field_value() maps each value to one representation at the
# boundary (RuleField construction) so equality is representation-independent.

_PROTO_NAME_TO_IANA = {
    'icmp': '1', 'tcp': '6', 'udp': '17', 'gre': '47', 'esp': '50', 'icmpv6': '58',
}

_IP_ADDRESS_FIELDS = frozenset([
    'packet.ipv4.source', 'packet.ipv4.destination',
    'packet.ipv6.source', 'packet.ipv6.destination',
])


def _canonical_ip(value: str) -> str:
    """ Compressed canonical form of an IP address or CIDR. A value that is not
    a parseable address (a wildcard/bit-vector string, a partial, 'any', ...) is
    returned unchanged. """
    try:
        if '/' in value:
            net = ipaddress.ip_network(value, strict=False)
            return '%s/%d' % (net.network_address.compressed, net.prefixlen)
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return value


def canonicalize_field_value(name: str, value: Any) -> Any:
    """ Map a field value to a single canonical representation so equivalent
    inputs compare equal: IPv4/IPv6 address fields to their compressed form and
    the protocol field to its IANA number.

    Idempotent and total: a non-string value (e.g. a Vector or None), a
    non-address/non-protocol field, an unparseable address, or an unknown
    protocol name is returned unchanged. The canonical value always yields the
    same bit-vector as the input, so verification semantics are unaffected.
    Field types whose values are read by keyword elsewhere (module.state,
    module, port names) are deliberately left untouched.
    """
    if not isinstance(value, str):
        return value
    if name in _IP_ADDRESS_FIELDS:
        return _canonical_ip(value)
    if name == 'packet.ipv6.proto':
        return _PROTO_NAME_TO_IANA.get(value, value)
    return value


def is_ip(ips: str) -> bool:
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


def is_domain(domains: str) -> bool:
    """ Checks if a string is a valid domain name.

    Keyword arguments:
    domains -- a string
    """
    labels = domains.split(".")
    label = re.compile("^[a-zA-Z](([-a-zA-Z0-9]+)?[a-zA-Z0-9])?$") # cf. RFC1025
    return all([re.match(label, l) for l in labels])


def is_unix(unixs: str) -> bool:
    """ Checks if a string is a valid unix domain socket address.

    Keyword arguments:
    unixs -- a string
    """
    return '\0' not in unixs


def is_port(ports: str) -> bool:
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


def is_ext_port(ports: str) -> bool:
    """ Checks if a string is a valid interface number.

    Keyword arguments:
    ports -- a string
    """
    return is_port(ports)


def is_host(hosts: str) -> bool:
    """ Checks if a string is a valid host identifier consisting of either of
        the form <domain>:<port> or <ip>:port.
    Keyword arguments:
    hosts -- a string
    """
    try:
        host, port = hosts.split(':')
    except ValueError:
        return False

    return (is_ip(host) or is_domain(host)) and is_port(port)


def normalize_vlan_tag(vlan: str) -> str:
    """ Normalizes vlan tags.

    Keyword arguments:
    vlan -- a vlan tag
    """

    vlan_tag = int(vlan)
    assert vlan_tag >= 0 and vlan_tag < 4096

    return '{:016b}'.format(vlan_tag) if vlan_tag != 0 else 'x'*16


def normalize_upper_port(port: str) -> str:
    """ Normalizes upper protocol port numbers.

    Keyword arguments:
    port -- a port number
    """

    portno = int(port)
    assert portno > 0 and portno < 65536

    return '{:016b}'.format(portno)


def normalize_ipv4_address(address: str) -> str:
    """ Normalizes an IPv4 address.

    Keyword arguments:
    address -- an IPv4 address in dotted or cidr notation
    """

    match = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$", address)
    if not match:
        raise ValueError("%s is not an ipv4 address" % address)

    cidr: Optional[str]
    try:
        addr, cidr = address.split('/')
    except ValueError:
        addr = address
        cidr = None

    addr = ''.join(["{:08b}".format(int(x)) for x in addr.split('.')])

    if cidr and int(cidr) < 32:
        clen = int(cidr)
        addr = addr[:clen] + 'x'*(32-clen)

    return addr


def normalize_ipv6_address(address: str) -> str:
    """ Normalizes an IPv6 address.

    Keyword arguments:
    address -- an IPv6 address in full, cidr, or short notation
    """

    cidr: Optional[str]
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

    lblocks = laddr.split(":") if laddr else []
    rblocks = raddr.split(":") if raddr else []

    blocks = lblocks + ["0"] * (8-len(lblocks)-len(rblocks)) + rblocks
    addr = "".join(["{:016b}".format(int(block, 16)) for block in blocks])

    if cidr and int(cidr) < 128:
        clen = int(cidr)
        addr = addr[:clen] + 'x'*(128-clen)

    return addr


def normalize_ipv6_proto(proto: str) -> str:
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


def normalize_ipv6header_header(header: str) -> str:
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



def _denormalize_ip_address(
        vector: str, alen: int, blen: int, bform: Callable[[int], str], delim: str
) -> str:
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


def denormalize_ipv4_address(vector: str) -> str:
    """ Converts a ternary bit vector to an IPv4 prefix representation

    Keyword arguments:
    vector - the ternary bit vector representing the IPv4 prefix
    """
    assert len(vector) == 32
    return _denormalize_ip_address(vector, 32, 8, str, '.')


def denormalize_ipv6_address(vector: str) -> str:
    """ Converts a ternary bit vector to an IPv6 prefix representation

    Keyword arguments:
    vector - the ternary bit vector representing the IPv6 prefix
    """
    assert len(vector) == 128
    return _denormalize_ip_address(vector, 128, 16, lambda x: hex(x)[2:], ':')


PORT_BITS = 16
def portrange_to_prefix_list(lower: int, upper: int) -> List[Tuple[int, int]]:
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
        for postfix in range(PORT_BITS+1):
            if (lower % (1 << (postfix + 1)) != 0) or (lower + (1 << (postfix + 1)) - 1 > upper):
                break

        res.append((lower, PORT_BITS - postfix))
        lower += (1 << postfix)

    return res


def portrange_to_prefixed_bitvectors(lower: int, upper: int) -> List[str]:
    """ Transforms a port range to a set of prefixed bit vectors.

    Arguments:
    lower -- the lower port
    upper -- the upper port
    """

    assert (lower <= upper)

    prefixes = portrange_to_prefix_list(lower, upper)

    res = []
    for base, prefix in prefixes:
        res.append("{:016b}".format(base)[:prefix] + "x" * (PORT_BITS - prefix))

    return res
