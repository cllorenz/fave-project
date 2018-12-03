""" This module provides packet constants and utilities.
"""

ETHER_TYPE_IPV4 = '00000100' # 4
ETHER_TYPE_IPV6 = '00000110' # 6

IP_PROTO_ICMPV6 = '00111010' # 58
IP_PROTO_TCP = '00000110'    # 6
IP_PROTO_UDP = '00010001'    # 17

IPV6_ROUTE = '00101011'      # 43
IPV6_HOP = '00000000'        # 0
IPV6_HBH = '00000000'        # 0
IPV6_DST = '00111100'        # 60
IPV6_FRAG = '00101100'       # 44
IPV6_AUTH = '00110011'       # 51
IPV6_ESP = '00110010'        # 50
IPV6_NONE = '00111011'       # 59
IPV6_PROT = '11111111'       # 255


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

    try:
        addr, cidr = address.split('/')
    except ValueError:
        addr = address
        cidr = None

    addr = ''.join(["{:08b}".format(int(x)) for x in addr.split('.')])

    if cidr and int(cidr) < 32:
        cidr = int(cidr)
        return addr[:cidr] + 'x'*(32-cidr)
    else:
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

    laddr, raddr = addr.split("::")
    laddr = laddr.split(":")
    if raddr:
        raddr = raddr.split(":")
        laddr += ["0"] * len(range(8-len(laddr)-len(raddr))) + raddr
    addr = "".join(["{:016b}".format(int(block, 16)) for block in laddr])

    if cidr and int(cidr) < 128:
        cidr = int(cidr)
        return addr[:cidr] + 'x'*(128-cidr)
    else:
        return addr


def normalize_ipv6_proto(proto):
    """ Normalizes the IPv6 upper protocol field (last next header field in chain).

    Keyword arguments:
    proto -- the protocol field value
    """

    return {
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
