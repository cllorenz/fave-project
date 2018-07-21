


ETHER_TYPE_IPV6 = '00000110' # 6

IP_PROTO_ICMPV6 = '00111010' # 58
IP_PROTO_TCP =    '00000110' # 6
IP_PROTO_UDP =    '00010001' # 17

IPV6_ROUTE = "00101011" # 43
IPV6_HOP =   "00000000" # 0
IPV6_HBH =   "00000000" # 0
IPV6_DST =   "00111100" # 60
IPV6_FRAG =  "00101100" # 44
IPV6_AUTH =  "00110011" # 51
IPV6_ESP =   "00110010" # 50


def normalize_upper_port(port):
    return '{:016b}'.format(int(port))

def normalize_ipv6_address(address):
    try:
        addr,cidr = address.split("/")
    except ValueError:
        addr = address
        cidr = None

    laddr,raddr = addr.split("::")
    laddr = laddr.split(":")
    if raddr:
        raddr = raddr.split(":")
        laddr += ["0" for _i in range(8-len(laddr)-len(raddr))] + raddr
    addr = "".join(["{:016b}".format(int(block,16)) for block in laddr])

    if cidr and int(cidr) < 128:
        cidr = int(cidr)
        return addr[:cidr] + 'x'*(128-cidr)
    else:
        return addr

def normalize_ipv6_proto(proto):
    return {
        "icmpv6"    : IP_PROTO_ICMPV6,
        "tcp"       : IP_PROTO_TCP,
        "udp"       : IP_PROTO_UDP,
    }[proto]


def normalize_ipv6header_header(header):
    return {
        "ipv6-route"    : IPV6_ROUTE,
        "hop"           : IPV6_HOP,
        "hop-by-hop"    : IPV6_HBH,
        "dst"           : IPV6_DST,
        "route"         : IPV6_ROUTE,
        "frag"          : IPV6_FRAG,
        "auth"          : IPV6_AUTH,
        "esp"           : IPV6_ESP,
        #"none"          : "", # XXX implement
        #"prot"          : ""  # XXX implement
    }[header]

