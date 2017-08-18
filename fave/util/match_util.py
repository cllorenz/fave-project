oxm_field_to_match_field = {
    'eth_src' : "packet.ether.source",
    'eth_dst' : "packet.ether.destination",
    'eth_type' : "packet.ether.type",
    'ipv4_src' : "packet.ipv4.source",
    'ipv4_dst' : "packet.ipv4.destination",
    'ipv6_src' : "packet.ipv6.source",
    'ipv6_dst' : "packet.ipv6.destination",
    'ip_proto' : "packet.ipv6.proto",
    'icmpv6_type' : "packet.ipv6.icmpv6.type",
    'ipv6_exthdr' : "module.ipv6header.header",
    'tcp_dst' : "packet.upper.dport",
    'tcp_src' : "packet.upper.sport",
    'udp_dst' : "packet.upper.dport",
    'upd_src' : "packet.upper.sport",
    'in_port' : 'interface'
}

