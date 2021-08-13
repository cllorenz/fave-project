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

from netplumber.jsonrpc import *

import socket


def prepare_network(sock,tables,links,sources,probes):
    nodes = []

    for t_idx,t_ports,table in tables:
        nodes.append([])
        add_table(sock,t_idx,t_ports)

        for rule in table:
            result = add_rule(sock,t_idx,*rule)
            nodes[t_idx-1].append(result)

    for link in links:
        add_link(sock,*link)

    for source in sources:
        add_source(sock,*source)

    for probe in probes:
        add_source_probe(sock,*probe)

    return nodes


def main():
    server = ('localhost',1234)
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.connect(server)
    init(sock,1)

    tables = [
        # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
        (1,[1,2,3],[# 11 11 11 11 11 11 11 01
            (1,[1],[2],"xxxxxxx0","x"*8,None),
            (2,[1],[3],"xxxxxxx1","x"*8,None)
        ]),
        (2,[4,5],[(1,[4],[5],"x"*8,"x"*8,None)]),
        (3,[6,7],[(1,[6],[7],"x"*8,"x"*8,None)]),
        (4,[8,9,10],[(1,[8,9],[10],"x"*8,"x"*8,None)])
    ]

    # (from_port,to_port)
    links = [(0,1),(2,4),(3,6),(5,8),(7,9),(10,11)]

    source = (["x"*8],None,[0])

    # ([ports],universal/existential,filter,test)
    probe = (
        [11],
#        "universal",
        "existential",
        {
            "type":"header",
            "header":{
                "list":["xxxxxxx1"],
                "diff":None
            }
        },{ # ^.*(t = 2).*(p = 1)$
            "type":"path",
            "pathlets":[
                {"type":"table","table":2},
                {"type":"port","port":1},
                {"type":"end"}
            ]
        }
    )

    init(sock,1)

    nodes = prepare_network(sock,tables,links,[source],[probe])

    # results in true probe condition
    remove_rule(sock,nodes[0][1])
    # results in false probe condition
    add_rule(sock,1,2,[1],[3],"xxxxxxx1","x"*8,None)

    print_plumbing_network(sock)


if __name__ == "__main__":
    main()
