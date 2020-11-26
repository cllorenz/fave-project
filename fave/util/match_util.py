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

""" This module provides utilities to convert match field identifier.
"""

OXM_FIELD_TO_MATCH_FIELD = {
    'eth_src' : "packet.ether.source",
    'eth_dst' : "packet.ether.destination",
    'eth_type' : "packet.ether.type",
    'vlan' : "packet.ether.vlan",
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
    'in_port' : 'in_port',
    'out_port' : 'out_port',
    'interface' : 'interface',
    'state' : 'module.conntrack.ctstate',
    'ctstate' : 'module.conntrack.ctstate',
    'packet.ether.source' : "packet.ether.source",
    'packet.ether.destination' : "packet.ether.destination",
    'packet.ether.type' : "packet.ether.type",
    'packet.ether.vlan' : "packet.ether.vlan",
    'packet.ipv4.source' : "packet.ipv4.source",
    'packet.ipv4.destination' : "packet.ipv4.destination",
    'packet.ipv6.source' : "packet.ipv6.source",
    'packet.ipv6.destination' : "packet.ipv6.destination",
    'packet.ipv6.proto' : "packet.ipv6.proto",
    'packet.ipv6.icmpv6.type' : "packet.ipv6.icmpv6.type",
    'module.ipv6header.header' : "module.ipv6header.header",
    'packet.upper.dport' : "packet.upper.dport",
    'packet.upper.sport' : "packet.upper.sport",
    'packet.upper.dport' : "packet.upper.dport",
    'packet.upper.sport' : "packet.upper.sport"
}
