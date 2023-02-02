#!/usr/bin/env python3

import ast
from pprint import pprint

PORTS="port_map.txt"
TOPO="backbone_topology.tf"

port_map = {}
inv_port_map = {}

with open(PORTS, 'r') as ports:
    switch = None
    for line in [l.rstrip() for l in ports.readlines()]:
        if line.startswith('$'):
            switch = line.lstrip('$')
        else:
            port_name, port_no = line.split(':')
            port_map[switch + '.' + port_name] = port_no
            inv_port_map[port_no] = switch + '.' + port_name

#pprint(inv_port_map, indent=2)

links = {}
inv_links = {}

with open(TOPO, 'r') as topo:
    for line in [l.rstrip() for l in topo.readlines() if l.startswith('link')]:
        _, src, _, _, _, _, _, dst, _, _, _, _, _, _ = line.split('$')
        src = str(int(src.lstrip('[').rstrip(']')) - 20000)
        dst = dst.lstrip('[').rstrip(']')

        links[src] = dst
#        if src in inv_port_map:
#            links[inv_port_map[src]] = inv_port_map.get(dst, "")
#        else:
#            print "unknown source", src
        inv_links[dst] = src
        #links[inv_port_map[src]] = inv_port_map[dst]

pprint(inv_links, indent=2)
pprint(links, indent=2)




TFS = {
    'atla.tf' : 100000,
    'chic.tf' : 200000,
    'hous.tf' : 300000,
    'kans.tf' : 400000,
    'losa.tf' : 500000,
    'newy32aoa.tf' : 600000,
    'salt.tf' : 700000,
    'seat.tf' : 800000,
    'wash.tf' : 900000
}

for TF in TFS:
    with open(TF, 'r') as tf:
        base_port = TFS[TF]
        for line in [l.rstrip() for l in tf.readlines() if l.startswith('fwd') or l.startswith('rw')]:
            _, in_ports, _, _, _, _, _, out_ports, _, _, _, _, _, _ = line.split('$')
            in_ports = ast.literal_eval(in_ports)
            out_ports = ast.literal_eval(out_ports)

            ing_connected = any([p == base_port or str(p) in inv_links for p in in_ports])
            for p in in_ports:
                if not str(p) in inv_links:
                    print(p)
#            print "connected ingress:", ing_connected
            egr_connected = any([str(p - 20000) in links for p in out_ports])
#            print "connected egress:", egr_connected
            fully_connected = ing_connected and egr_connected

            if fully_connected:
                print("fully connected rule:", line)
