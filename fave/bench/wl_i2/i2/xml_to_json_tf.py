#!/usr/bin/env python2

import json
from xml.dom import minidom

from util.packet_util import normalize_ipv4_address, normalize_ipv6_address
from netplumber.vector import Vector, set_field_in_vector

def make_rule(mapping, ports, is_ipv4, tid, rid, _len, address, out_ports):
    match = Vector(mapping['length'])
    field = 'packet.ipv4.destination' if is_ipv4 else 'packet.ipv6.destination'

    if is_ipv4:
        fvec = normalize_ipv4_address(address)
    else:
        try:
            fvec = normalize_ipv6_address(address)
        except ValueError:
            print address
            raise

    set_field_in_vector(mapping, match, field, fvec)

    return {
        'action' : 'fwd',
        'id' : tid + rid,
        'in_ports' : [],
        'out_ports' : [ports[p] for p in out_ports],
        'match' : match.vector
    }


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
    for port in pair.values():
        if port not in ports:
            router, _interface = port.split(':')
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
            line = table.next()

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
                for _ in range(3): table.next()

            tokens = line.split()

            if len(tokens) == 0:
                continue

            elif len(tokens) == 1:
                dst = tokens[0]
                line = table.next()

                tokens = line.split()
                if len(tokens) == 3:
                    _type, _rtref, _next_hop = tokens

                    line = table.next()
                    tokens = line.split()

                    if len(tokens) == 3:
                        _type, _index, _nhref = tokens
                        # XXX

                elif len(tokens) < 7:
                    pass
                    # XXX

                elif tokens[3] == 'ucst':
                    _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                else:
                    print "unknown action", len(tokens), tokens
                    break

            elif len(tokens) == 3:
                if tokens[0] == 'locl':
                    _type, _nhref, _nhref = tokens

                if tokens[0] == 'mcrt':
                    _type, _index, _nhref = tokens
                    # XXX

                else:
                    print "unknown action", len(tokens), tokens

            elif len(tokens) == 4:
                dst, _type, _rtref, _next_hop = tokens
                line = table.next()
                tokens = line.split()

                if len(tokens) == 4:
                    _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                else:
                    print tokens
                    break


            elif len(tokens) == 6:
                action = tokens[3]
                if action == 'ucst':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    line = table.next()
                    _next_hop, _type, _index, _nhref, interface = line.split()
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')), dst, [if_name]))

                elif action == 'indr':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    line = table.next()
                    tokens = line.split()
                    if len(tokens) == 1:
                        _next_hop = tokens[0]
                        line = table.next()
                        tokens = line.split()
                        _type, _index, _nhref, interface = tokens
                        if_name = router_name + interface
                        if if_name not in ports:
                            _tid, pid = tables[router_name]
                            tables[router_name] = (tid, pid+1)
                            ports[if_name] = (tid << 16) + pid + 1
                        routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                    elif len(tokens) == 5:
                        _next_hop, _type, _index, _nhref, interface = tokens
                        if_name = router_name + interface
                        if if_name not in ports:
                            _tid, pid = tables[router_name]
                            tables[router_name] = (tid, pid+1)
                            ports[if_name] = (tid << 16) + pid + 1
                        routing_table.append((int(dst.split('/')[1]), dst, [if_name]))


                elif action == 'dscd':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                elif action == 'ulst':
                    dst, _type, _rtref, _type, _index, _nhref = tokens
                    table.next()
                    line = table.next()
                    _next_hop, _type, _index, _nhref, if_1 = line.split()
                    table.next()
                    line = table.next()
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
                    print "unknown action:", action, len(tokens), tokens
                    break


            elif len(tokens) == 7:
                if tokens[3] == 'rslv':
                    dst, _type, _rtref, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    # XXX

                elif tokens[3] == 'ucst':
                    dst, _type, _rtref, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))


                elif tokens[4] == 'locl':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref = tokens
                    # XXX

                elif tokens[4] == 'mcst':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref = tokens
                    # XXX


                else:
                    print "unknown action", len(tokens), tokens
                    break


            elif len(tokens) == 8:
                action = tokens[4]
                if action == 'ucst':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, [if_name]))

                elif action == 'recv':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    # XXX

                elif action == 'bcst':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    # XXX

                elif action == 'dscd':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, _interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                elif action == 'hold':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    # XXX

                elif action == 'rjct':
                    dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                    if_name = router_name + interface
                    if if_name not in ports:
                        _tid, pid = tables[router_name]
                        tables[router_name] = (tid, pid+1)
                        ports[if_name] = (tid << 16) + pid + 1
                    routing_table.append((int(dst.split('/')[1]), dst, []))

                else:
                    print "unknown action", action, len(tokens), tokens
                    break

            else:
                print "could not parse:", tokens

        table_ipv4 = [make_rule(
            mapping, ports, True, tid, rid, *items
        ) for rid, items  in enumerate(sorted(routing_table_ipv4, reverse=True))]
        len_ipv4 = len(table_ipv4)

        table_ipv6 = [make_rule(
            mapping, ports, False, tid, rid + len_ipv4, *items
        ) for rid, items  in enumerate(sorted(routing_table_ipv6, reverse=True))]

        default_ipv4 = [default_rules[0]]
        default_ipv4 = [make_rule(
            mapping, ports, True, tid, 65533, *items
        ) for items in default_ipv4]

        default_ipv6 = [default_rules[1]]
        default_ipv6 = [make_rule(
            mapping, ports, False, tid, 65534, *items
        ) for items in default_ipv6]

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

        print router_file, len(table_ipv4 + table_ipv6 + default_rules)
        total += len(table_ipv4 + table_ipv6 + default_rules)

print "total:", total

topology_numbers = []
for pair in topology_names['topology']:
    topology_numbers.append({'src' : ports[pair['src']], 'dst' : ports[pair['dst']]})

json.dump(
    {'topology' : topology_numbers},
    open("bench/wl_i2/i2_tfs/topology.json", 'w'),
    indent=2
)
