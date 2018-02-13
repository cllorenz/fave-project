#!/usr/bin/env python2

import unittest
import os

import socket
import sys
import json
import random
from netplumber.jsonrpc import *

def generate_random_rule(idx,in_ports,out_ports,length):
    gen_wc = lambda x: "".join(["01x"[random.randint(0,2)] for _i in range(x)])
    gen_ports = lambda ports: [p for p in ports if random.randint(0,1) == 1]

    ip = []
    # potential infinite loop...
    # though, it would be strange randomness if this happened
    while ip == []:
        ip = gen_ports(in_ports)

    op = gen_ports(out_ports)

    match = gen_wc(length)
    mask = gen_wc(length)
    rw = gen_wc(length)

    return (idx,ip,op,match,mask,rw)


class TestRPC(unittest.TestCase):
    def setUp(self):
        os.system('scripts/start_np.sh')
        server = ('localhost',1234)
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.sock.connect(server)
        init(self.sock,1)


    def tearDown(self):
        reset_plumbing_network(self.sock)
        self.sock.close()
        os.system('scripts/stop_np.sh')


    def prepare_network(self,tables,links,sources,probes):
        nodes = []

        for t_idx,t_ports,table in tables:
            nodes.append([])
            add_table(self.sock,t_idx,t_ports)

            for rule in table:
                result = add_rule(self.sock,t_idx,*rule)
                nodes[t_idx-1].append(result)

        for link in links:
            add_link(self.sock,*link)

        for source in sources:
            add_source(self.sock,*source)

        for probe in probes:
            add_source_probe(self.sock,*probe)

        return nodes


    def test_basic(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2,3],[
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

        # ([ports],{universal,existential},filter,test)
        probe = (
            [11],
            "universal",
            {
                "type":"header",
                "header":{
                    "list":["x"*8],
                    "diff":None
                }
            },{
                "type":"path",
                "pathlets":[
                    {"type":"table","table":2},
                    {"type":"port","port":1},
                    {"type":"end"}
                ]
            }
        )

        init(self.sock,1)

        nodes = self.prepare_network(tables,links,[source],[probe])

        # results in true probe condition
        remove_rule(self.sock,nodes[0][1])
        # results in false probe condition
        add_rule(self.sock,1,2,[1],[3],"xxxxxxx1","x"*8,None)

        print_plumbing_network(self.sock)


    def test_advanced(self):
        tables = [
            (1,[11,12,13,14,19],[
                (1,[12,13,19],[11],"xxxx0110xxxxxx11","x"*16,None),
                (2,[14],[12],"xxxx1001xxxxxxxx","x"*16,None),
                (3,[14],[13],"xxxx1010xxxxxxxx","x"*16,None)
            ]),
            (2,[21,22,23,24,29],[
                (1,[21,23,24,29],[22],"xxxx0110xxxxxx11","x"*16,None),
                (2,[21],[24],"xxxx1010xxxxxxxx","x"*16,None)
            ]),
            (3,[31,32,33,34,35,36,39],[
                (1,[32,34],[33],"xxxx1000xxxxxx11","x"*16,None),
                (2,[31,33,34,35,36,39],[32],"xxxx0110xxxxxx11","x"*16,None),
    #            (3,[31],[33],"xxxx1001xxxxxx11","x"*16,"xxxx1000xxxxxx11"),
                (4,[31],[34],"xxxx1001xxxxxxxx","x"*16,None)
            ]),
            (4,[41,42,43,44,45,49],[
                (1,[41,42,44,49],[43],"xxxx0111xxxxxx11","x"*16,None),
                (2,[41],[45],"xxxx1010xxxxxxxx","x"*16,None)
            ]),
            (5,[51,52,54,53,59],[
                (1,[52],[51],"xxxx1000xxxxxx11","x"*16,None),
                (2,[51,53,59],[52],"xxxx0111xxxxxx11","x"*16,None),
                (3,[51],[54],"xxxx1001xxxxxxxx","x"*16,None)
            ]),
            (6,[61,62,63],[
                (1,[61,62,63],[63],"xxxx0110xxxxxx11","x"*16,"01101000xxxxxx11"),
                (2,[61,62,63],[],"x"*16,"x"*16,None)
            ]),
            (7,[71,72],[
                (1,[71,72],[72],"xxxx0111xxxxxx11","x"*16,"01111000xxxxxx11"),
                (2,[71,72],[],"x"*16,"x"*16,None)
            ]),
            (8,[81,89],[
                (1,[81],[89],"xxxx1000xxxxxx11","x"*16,None),
                (2,[89],[81],"1000xxxxxxxxxxxx","x"*16,None)
            ]),
        ]

        links = [
            (91,19),(92,29),(93,39),(94,49),(95,59),(96,14),
            (89,99),
            (11,61),(22,62),(32,63),(43,71),(52,72),
            (61,11),(62,22),(63,32),(71,43),(72,52),
            (33,81),(81,33),
            (12,31),(13,21),(31,12),(21,13),
            (23,36),(24,41),(36,23),(41,24),
            (34,51),(35,42),(51,34),(42,35),
            (44,53),(53,44)
        ]

        sources = [
            (["00010110xxxxxx11"],None,[91]),
            (["00100110xxxxxx11"],None,[92]),
            (["00110110xxxxxx11"],None,[93]),
            (["01000111xxxxxx11"],None,[94]),
            (["01010111xxxxxx11"],None,[95]),
            (["x"*16],[
                "00010110xxxxxx11",
                "00100110xxxxxx11",
                "00110110xxxxxx11",
                "01000111xxxxxx11",
                "01010111xxxxxx11"
            ],[96])
        ]

        probe = (
            [99],
            "universal",
            {
                "type":"header",
                "header":{
                    "list":["xxxx1000xxxxxx11"],
                    "diff":None
                }
            },{
                "type":"or",
                "arg1":{
                    "type":"path",
                    "pathlets":[
                        {"type":"table","table":6},
                        {"type":"last_ports","ports":[19,29,39,49,59]},
                    ]
                },
                "arg2":{
                    "type":"path",
                    "pathlets":[
                        {"type":"table","table":7},
                        {"type":"last_ports","ports":[19,29,39,49,59]},
                    ]
                }
            }
        )

        init(self.sock,2)

        nodes = self.prepare_network(tables,links,sources,[probe])

        # results in false probe condition
        remove_rule(self.sock,nodes[2][2])
        result = add_rule(self.sock,3,3,[31],[33],"xxxx1001xxxxxx11","x"*16,"xxxx1000xxxxxx11")

        # results in true probe condition
        remove_rule(self.sock,result)
        add_rule(self.sock,3,4,[31],[34],"xxxx1001xxxxxxxx","x"*16,None)


    def test_cycle(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2],[(1,[1],[2],"x"*8,"x"*8,None)]),
            (2,[3,4],[]),
        ]

        links = [(2,3),(4,1),(99,1)]

        sources = [(["x"*8],None,[99])]
        probes = []

        init(self.sock,1)

        nodes = self.prepare_network(tables,links,sources,probes)

        # add new rule to close the cycle
        add_rule(self.sock,*(2,1,[3],[4],"x"*8,"x"*8,None))


    def _test_slicing(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2],[(1,[1],[2],"xxxxx110","x"*8,None)]),
            (2,[3,4],[(1,[3],[4],"xxxxxx10","x"*8,None)]),
            (3,[5,6],[(1,[5],[6],"xxxxxxx0","x"*8,None)])
        ]

        # (from_port,to_port)
        links = [(2,3),(4,5)]

        sources = []
        probes = []

        init(self.sock,1)

        nodes = self.prepare_network(tables,links,sources,probes)

        # add new rule which will be put in new slice
        add_rule(self.sock,*(1,2,[1],[2],"xxxxx111","x"*8,None))

        # setup slice
        add_slice(self.sock,1,*(["xxxxx1x1"],None))

        # add slice to introduce overlap
        add_slice(self.sock,2,*(["xxxxx111"],None))
        remove_slice(self.sock,2)

        result = add_rule(self.sock,*(1,3,[1],[2],"xxxxxx1x","x"*8,None))
        remove_rule(self.sock,result)

        # add rule to introduce leakage
        result = add_rule(self.sock,*(2,2,[3],[4],"xxxxx111","x"*8,"xxxxx110"))
        remove_rule(self.sock,result)

        # remove slice
        remove_slice(self.sock,1)


    def _test_fw(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2],[(1,[1],[2],"x"*8,"x"*8,None)]),
            (2,[3,4],[]),
            (3,[5,6],[(1,[5],[6],"x"*8,"x"*8,None)])
        ]

        # (from_port,to_port)
        links = [(2,3),(4,5)]

        sources = [(["x"*8],None,[1])]
        probes = []

        init(self.sock,1)

        nodes = self.prepare_network(tables,links,sources,probes)

        # add new rule which drops some traffic
        r2 = add_fw_rule(self.sock,*(2,2,[3],[],{"list":["x"*8],"diff":None}))
        assert(r2 != 0)

        # add new rule which allows some traffic
        r1 = add_fw_rule(self.sock,*(2,1,[3],[4],{"list":["xxxxxx11"],"diff":None}))
        assert(r1 != 0)

        # try to add normal rule to firewall, should fail
        r3 = add_rule(self.sock,*(2,3,[3],[4],"x"*8,"x"*8,None))
        assert(r3 == 0)

        # try to add firewall rule to normal table, should fail
        r4 = add_fw_rule(self.sock,*(1,2,[1],[2],{"list":["x"*8],"diff":None}))
        assert(r4 == 0)

        remove_fw_rule(self.sock,r1)

        # try to add firewall rule to former normal table, should succeed
        remove_rule(self.sock,nodes[0][0])
        r5 = add_fw_rule(sock,1,1,[1],[2],{"list":["x"*8],"diff":None})
        assert(r5 != 0)

        remove_fw_rule(self.sock,r2)

        # try to add normal rule to former firewall table, should succeed
        r6 = add_rule(self.sock,2,1,[3],[4],"x"*8,"x"*8,None)
        assert(r6 != 0)


    def _test_policy(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2],[(1,[1],[2],"x"*8,"x"*8,None)]),
            (2,[3,4],[]),
            (3,[5,6],[(1,[5],[6],"x"*8,"x"*8,None)])
        ]

        # (from_port,to_port)
        links = [(2,3),(4,5)]

        sources = [(["x"*8],None,[99])]
        probes = []

        init(self.sock,1)

        nodes = self.prepare_network(tables,links,sources,probes)

        # add policy probe node
        add_policy_probe(self.sock,[7])
        add_link(self.sock,6,7)
        add_link(self.sock,99,1)

        # add policy rules
        add_policy_rule(self.sock,2,{"list":["xxxxxx11"],"diff":None},"allow")
        add_policy_rule(self.sock,2,{"list":["x"*8],"diff":None},"deny")

        # add uncritical rule
        add_rule(self.sock,*(2,1,[3],[4],"xxxxx111","x"*8,None))

        # add critical rule
        add_rule(self.sock,*(2,2,[3],[4],"xxxxxx11","x"*8,"xxxxxx10"))

        print_plumbing_network(self.sock)


    def test_rule_unreachability(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2],[
                (1,[],[2],"10xxxxxx","x"*8,None),
                (2,[],[2],"01xxxxxx","x"*8,None),
                (3,[],[2],"00xxxxxx","x"*8,None)
            ])
        ]

        init(self.sock,1)
        nodes = self.prepare_network(tables,[],[],[])

        # add rule that completes the matching
        add_rule(self.sock,*(1,4,[],[2],"11xxxxxx","x"*8,None))

        # add unreachable rule
        add_rule(self.sock,*(1,5,[],[2],"xx1xxxxx","x"*8,None))

        print_plumbing_network(self.sock)


    def test_rule_shadowing(self):
        tables = [
            # (t_idx,t_ports,[(r_idx,[in_ports],[out_ports],match,mask,rw)])
            (1,[1,2],[
                (1,[],[2],"10xxxxxx","x"*8,None),
                (2,[],[2],"01xxxxxx","x"*8,None),
                (3,[],[2],"00xxxxxx","x"*8,None)
            ])
        ]

        init(self.sock,1)
        nodes = self.prepare_network(tables,[],[],[])

        # add shadowed rule
        add_rule(self.sock,*(1,4,[],[2],"011xxxxx","x"*8,None))

        # add unshadowed rule
        add_rule(self.sock,*(1,5,[],[2],"11xxxxxx","x"*8,None))


    def expand_test(self):
        rules = [generate_random_rule(i,[1,2],[1,2],160) for i in range(0,50)]

        tables = [
            (1,[1,2],rules)
        ]

        links = [(99,1)]
        sources = [(["x"*160],None,[99])]
    #    sources = [] # TODO: fix regression!!!
        probes = []

        init(self.sock,1)
        # initially exand wildcard vector size
        expand(self.sock,160)

        nodes = self.prepare_network(tables,links,sources,probes)

        # double wildcard size
        expand(self.sock,320)

        # add rule with new size
        rule = generate_random_rule(100,[1,2],[1,2],320)
        add_rule(self.sock,1,*rule)


if __name__ == '__main__':
    unittest.main()
