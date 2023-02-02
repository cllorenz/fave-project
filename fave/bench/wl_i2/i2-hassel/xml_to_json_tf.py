#!/usr/bin/env python3

import json
from xml.dom import minidom
from copy import deepcopy

from util.packet_util import normalize_ipv4_address, normalize_ipv6_address, normalize_vlan_tag
from netplumber.vector import Vector, set_field_in_vector
from functools import reduce

ipv6_prefix = normalize_ipv6_address('64:ff9b::/96')[:96]

def make_rule(mapping, ports, ae_bundles, is_ipv4, tid, rid, _len, address, out_ports):
    match = Vector(mapping['length'])
    field = 'packet.ipv4.destination' if is_ipv4 else 'packet.ipv6.destination'

    if is_ipv4:
        fvec = ipv6_prefix + normalize_ipv4_address(address)
        #fvec = normalize_ipv4_address(address)
    else:
        try:
            fvec = normalize_ipv6_address(address)
        except ValueError:
            print(address)
            raise

#    set_field_in_vector(mapping, match, field, fvec)
    set_field_in_vector(mapping, match, 'packet.ipv6.destination', fvec)

    rules = []
    for port in out_ports:
        if "ae" in port:
            router, ae_name = port.split(':')
            ae_ports = ae_bundles[router][ae_name]

            for ae_port in ae_ports:
                out_port, vlan = ae_port.split('.')

#                mask = Vector(length=mapping['length'])
#                set_field_in_vector(mapping, mask, 'packet.ether.vlan', '1'*16)

#                rewrite = Vector(length=mapping['length'])
#                set_field_in_vector(mapping, rewrite, 'packet.ether.vlan', normalize_vlan_tag(vlan))

                in_ports = [
                    ae_in.split('.')[0] for ae_in in ae_ports if ae_in != ae_port
                ]

                set_field_in_vector(mapping, match, 'packet.ether.vlan', normalize_vlan_tag(vlan))

                rules.append({
                    'action' : 'fwd',
                    'id' : tid + rid,
                    'in_ports' : [ports[router + ':' + in_port] for in_port in in_ports],
                    'out_ports' : [ports[router + ':' + out_port]],
                    'match' : deepcopy(match.vector)
#                    'mask' : mask.vector,
#                    'rewrite' : rewrite.vector
                })

        elif 'dsc' in port:
            continue


        elif '.' in port:
            out_port, vlan = port.split('.')

            mask = Vector(length=mapping['length'])
            set_field_in_vector(mapping, mask, 'packet.ether.vlan', '1'*16)

            rewrite = Vector(length=mapping['length'])
            set_field_in_vector(mapping, rewrite, 'packet.ether.vlan', normalize_vlan_tag(vlan))

            set_field_in_vector(mapping, match, 'packet.ether.vlan', normalize_vlan_tag(vlan))

            rules.append({
                'action' : 'fwd',
                'id' : tid + rid,
                'in_ports' : [],
                'out_ports' : [ports[out_port]],
                'match' : deepcopy(match.vector),
                'mask' : mask.vector,
                'rewrite' : rewrite.vector
            })

        else:
            rules.append({
                'action' : 'fwd',
                'id' : tid + rid,
                'in_ports' : [],
                'out_ports' : [ports[port]],
                'match' : deepcopy(match.vector)
            })

    return rules


router_files = [
    "bench/wl_i2/i2/atla-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/chic-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/hous-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/kans-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/losa-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/newy32aoa-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/salt-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/seat-show_route_forwarding-table_table_default.xml",
    "bench/wl_i2/i2/wash-show_route_forwarding-table_table_default.xml"
]

mapping = json.load(open("bench/wl_i2/mapping.json", 'r'))
vec_length = mapping['length']

topology_names = json.load(open("bench/wl_i2/i2/topology_names.json", "r"))

ae_bundles = json.load(open("bench/wl_i2/i2_tfs/bundles.json", "r"))

tables = {
    'atla' : (1, 0),
    'chic' : (2, 0),
    'hous' : (3, 0),
    'kans' : (4, 0),
    'losa' : (5, 0),
    'newy32aoa' : (6, 0),
    'salt' : (7, 0),
    'seat' : (8, 0),
    'wash' : (9, 0)
}

ports = {}
for pair in topology_names['topology']:
    for port in list(pair.values()):
        if port not in ports:
            router, _interface = port.split(':')
            tid, pid = tables[router]
            tables[router] = (tid, pid+1)

            ports[port] = (tid << 16) + pid + 1


for router, bundle in ae_bundles.items():
    for _ae_name, ae_ports in bundle.items():
        for ae_port in ae_ports:
            port = router + ':' + ae_port.split('.')[0]
            tid, pid = tables[router]
            tables[router] = (tid, pid+1)

            ports[port] = (tid << 16) + pid + 1

total = 0
for router_file in router_files:
    root = minidom.parse(router_file)

    routers = root.getElementsByTagName("router")
    for router in routers:
        router_name = router.getAttribute("name")

        tid, _pid = tables[router_name]

        routing_table_ipv6 = []
        routing_table_ipv4 = []
        routing_table = None
        default_rule = None
        dst_proto = None
        default_addr = None
        default_rules = []

        table = iter([l for l in router.childNodes[0].data.split("\n") if l])
        while True:
            line = next(table)

            if line.startswith("Routing table: default.mpls"):
                break

            elif line.startswith("Routing table: default.inet6"):
                routing_table = routing_table_ipv6
                dst_proto = 'packet.ipv6.destination'
                default_addr = '0::0/0'
                continue

            elif line.startswith("Routing table: default.inet"):
                routing_table = routing_table_ipv4
                dst_proto = 'packet.ipv4.destination'
                default_addr = '0.0.0.0/0'
                continue

            elif line.startswith("Destination") or line.startswith("Routing") or line.startswith("Internet"):
                continue

            elif line.startswith("ISO"):
                for _ in range(3): next(table)

            tokens = line.split()

            if len(tokens) == 0:
                continue

            elif len(tokens) == 1:
                dst = tokens[0]
                line = next(table)

                tokens = line.split()
                if len(tokens) == 3:
                    _type, _rtref, _next_hop = tokens

                    line = next(table)
                    tokens = line.split()

                    if len(tokens) == 3:
                        _type, _index, _nhref = tokens
                        # XXX

                elif len(tokens) < 7:
                    pass
                    # XXX

                elif tokens[3] == 'ucst':
                    _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                else:
                    print("unknown action", len(tokens), tokens)
                    break

            elif len(tokens) == 3:
                if tokens[0] == 'locl':
                    _type, _nhref, _nhref = tokens

                if tokens[0] == 'mcrt':
                    _type, _index, _nhref = tokens
                    # XXX

                else:
                    print("unknown action", len(tokens), tokens)

            elif len(tokens) == 4:
                dst, _type, _rtref, _next_hop = tokens
                line = next(table)
                tokens = line.split()

                if len(tokens) == 4:
                    _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                else:
                    break


            elif len(tokens) == 6:
                action = tokens[3]
                if action == 'ucst':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    line = next(table)
                    _next_hop, _type, _index, _nhref, interface = line.split()
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')), dst, [if_name]))

                elif action == 'indr':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    line = next(table)
                    tokens = line.split()
                    if len(tokens) == 1:
                        _next_hop = tokens[0]
                        line = next(table)
                        tokens = line.split()
                        _type, _index, _nhref, interface = tokens
                        if_name = router_name + ':' + interface
                        pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                        if pif_name not in ports:
                            _tid, pid = tables[router_name]
                            tables[router_name] = (tid, pid+1)
                            ports[pif_name] = (tid << 16) + pid + 1
                        routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                    elif len(tokens) == 5:
                        _next_hop, _type, _index, _nhref, interface = tokens
                        if_name = router_name + ':' + interface
                        pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                        if pif_name not in ports:
                            _tid, pid = tables[router_name]
                            tables[router_name] = (tid, pid+1)
                            ports[pif_name] = (tid << 16) + pid + 1
                        routing_table.append((int(dst.split('/')[1]), dst, [if_name]))


                elif action == 'dscd':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                elif action == 'ulst':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    next(table)
                    line = next(table)
                    _next_hop, _type, _index, _nhref, if_1 = line.split()
                    next(table)
                    line = next(table)
                    _next_hop, _type, _index, _nhref, if_2 = line.split()
                    # XXX

                elif action == 'rslv':
                    dst, _type, _rtref, _type, _index, _nhref = tokens

                elif action == 'mdsc':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                elif action == 'bcst':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    # XXX

                elif action == 'rjct':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    if dst == 'default':
                        default_rules.append((0, default_addr, []))
                    else:
                        routing_table.append((int(dst.split('/')[1]), dst, []))

                else:
                    print("unknown action:", action, len(tokens), tokens)
                    break


            elif len(tokens) == 7:
                if tokens[3] == 'rslv':
                    dst, _type, _rtref, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    # XXX

                elif tokens[3] == 'ucst':
                    dst, _type, _rtref, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))


                elif tokens[4] == 'locl':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref = tokens
                    # XXX

                elif tokens[4] == 'mcst':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref = tokens
                    # XXX


                else:
                    print("unknown action", len(tokens), tokens)
                    break


            elif len(tokens) == 8:
                action = tokens[4]
                if action == 'ucst':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                elif action == 'recv':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    # XXX

                elif action == 'bcst':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    # XXX

                elif action == 'dscd':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, _interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                elif action == 'hold':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface.split('.')[0]
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    # XXX

                elif action == 'rjct':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + ':' + interface
                    pif_name = if_name.split('.')[0] if '.' in if_name else if_name
                    if pif_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[pif_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                else:
                    print("unknown action", action, len(tokens), tokens)
                    break

            else:
                print("could not parse:", tokens)

        table_ipv4 = reduce(lambda x, y: x + y, [make_rule(
            mapping, ports, ae_bundles, True, tid, rid, *items
        ) for rid, items  in enumerate(sorted(routing_table_ipv4, reverse=True))], [])
        len_ipv4 = len(table_ipv4)

        table_ipv6 = reduce(lambda x, y: x + y, [make_rule(
            mapping, ports, ae_bundles, False, tid, rid + len_ipv4, *items
        ) for rid, items  in enumerate(sorted(routing_table_ipv6, reverse=True))], [])

        default_ipv4 = [default_rules[0]] if len(default_rules) > 0 else []
        default_ipv4 = reduce(lambda x, y: x + y, [make_rule(
            mapping, ports, ae_bundles, True, tid, 65533, *items
        ) for items in default_ipv4], [])

        default_ipv6 = [default_rules[1]] if len(default_rules) > 1 else []
        default_ipv6 = reduce(lambda x, y: x + y, [make_rule(
            mapping, ports, ae_bundles, False, tid, 65534, *items
        ) for items in default_ipv6], [])

        default_rules = default_ipv4 + default_ipv6

        _tid, pid = tables[router_name]
        table = {
            'rules' : table_ipv4 + table_ipv6 + default_rules,
            'id' : tid,
            'ports' : [(tid << 16) + i for i in range(1, pid+1)]
        }

        json.dump(
            table,
            open('bench/wl_i2/i2_tfs/' + router_name + '.tf.json', 'w'),
            indent=2
        )

        print(router_file, len(table_ipv4 + table_ipv6 + default_rules))
        total += len(table_ipv4 + table_ipv6 + default_rules)

print("total:", total)

topology_numbers = []
for pair in topology_names['topology']:
    topology_numbers.append({'src' : ports[pair['src']], 'dst' : ports[pair['dst']]})

json.dump(
    {'topology' : topology_numbers},
    open("bench/wl_i2/i2_tfs/topology.json", 'w'),
    indent=2
)
