#!/usr/bin/env python2

import os
import json
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import Vector
from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies
from bench.bench_helpers import is_intermediate_port, is_output_port, pick_port, array_ipv4_to_cidr, array_vlan_to_number, array_to_int

ROLES='bench/wl_stanford/roles.txt'
POLICY='bench/wl_stanford/reach.txt'
REACH='bench/wl_stanford/reach.csv'

CHECKS='bench/wl_stanford/checks.json'

TOPOLOGY='bench/wl_stanford/stanford-json/topology.json'
ROUTES='bench/wl_stanford/stanford-json/routes.json'
SOURCES='bench/wl_stanford/stanford-json/sources.json'

with open('bench/wl_stanford/stanford-json/mapping.json', 'r') as mf:
    MAPPING = Mapping.from_json(json.loads(mf.read()))


def get_start_end(field):
    start = MAPPING[field]
    end = start + FIELD_SIZES[field]
    return start, end


def _get_field_from_match(match, fname, sname, convert):
    res = None
    start, end = get_start_end(fname)
    field_match = match[start:end]
    if field_match != 'x'*FIELD_SIZES[fname]:
        res = "%s=%s" % (sname, convert(field_match))
    return res


def _get_rewrite(rewrite, mask, fname, sname, convert, default=None):
    res = None
    start, end = get_start_end(fname)
    field_mask = mask[start:end]
    field_rewrite = rewrite[start:end]
    if field_mask == '0'*FIELD_SIZES[fname]:
        res = "%s:%s" % (sname, convert(field_rewrite))

    return res





def rule_to_route(rule, base_port, ext_port):
    rid = int(rule['id']) & 0xffff

    in_ports = rule['in_ports']
    if not any([is_intermediate_port(p, base_port) for p in in_ports]):
        in_ports.append(ext_port)
    out_ports = rule['out_ports']

    match_fields = []

    match = rule['match'].replace(',', '')

    src = _get_field_from_match(
        match, 'packet.ipv4.source', 'ipv4_src', array_ipv4_to_cidr
    )
    if src: match_fields.append(src)

    dst = _get_field_from_match(
        match, 'packet.ipv4.destination', 'ipv4_dst', array_ipv4_to_cidr
    )
    if dst: match_fields.append(dst)

    vlan = _get_field_from_match(
        match, 'packet.ether.vlan', 'vlan', array_vlan_to_number
    )
    if vlan: match_fields.append(vlan)

    start, end = get_start_end('packet.ipv6.proto')
    if match[start:end] not in ['x'*FIELD_SIZES['packet.ipv6.proto'], '0'*FIELD_SIZES['packet.ipv6.proto']]:
        proto = "ip_proto=%s" % int(match[start:end], 2)
        match_fields.append(proto)


    sport = _get_field_from_match(
        match, 'packet.upper.sport', 'tcp_src', array_to_int
    )
    if sport: match_fields.append(sport)

    dport = _get_field_from_match(
        match, 'packet.upper.sport', 'tcp_dst', array_to_int
    )
    if dport: match_fields.append(dport)

    flags = _get_field_from_match(
        match, 'packet.upper.tcp.flags', 'tcp_flags', array_to_int
    )
    if flags: match_fields.append(flags)

    actions = []

    if rule['action'] == 'rw':
        mask = rule['mask'].replace(',', '')
        rewrite = rule['rewrite'].replace(',', '')

        fields = []

        src_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.ipv4.source',
            'ipv4_dst',
            array_ipv4_to_cidr,
            default='0.0.0.0/0'
        )
        if src_rw: fields.append(src_rw)

        dst_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.ipv4.destination',
            'ipv4_dst',
            array_ipv4_to_cidr,
            default='0.0.0.0/0'
        )
        if dst_rw: fields.append(dst_rw)

        vlan_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.ether.vlan',
            'vlan',
            array_vlan_to_number
        )
        if vlan_rw: fields.append(vlan_rw)


        proto_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.ipv6.proto',
            'ip_proto',
            array_to_int
        )
        if proto_rw: fields.append(proto_rw)

        sport_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.upper.sport',
            'tcp_src',
            array_to_int
        )
        if sport_rw: fields.append(sport_rw)

        dport_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.upper.dport',
            'tcp_dst',
            array_to_int
        )
        if dport_rw: fields.append(dport_rw)

        flags_rw = _get_rewrite(
            rewrite,
            mask,
            'packet.upper.tcp.flags',
            'tcp_flags',
            array_to_int
        )
        if flags_rw: fields.append(flags_rw)


        if fields != []:
            actions.append("rw=%s" % ';'.join(fields))

    actions.extend(["fd=%s" % port_to_name[p] for p in out_ports])

    return (
        name, 1, rid, match_fields, actions,
        [port_to_name[p] for p in in_ports]
    )

def _read_port_map(pmf):
    get_port = lambda l: int(l.split(':')[1])
    port_map = {}
    with open(pmf, 'r') as f:
        router = ""
        for line in [l.rstrip() for l in f.readlines()]:
            if line.startswith('$'):
                router = line.lstrip('$')
            else:
                port_map[get_port(line)] = router

    return port_map


if __name__ == '__main__':
    use_unix = True

    os.system("mkdir -p /dev/shm/np")
    os.system("rm -rf /dev/shm/np/*")
    os.system("rm -f /dev/shm/*.socket")

    os.system(
        "python2 ../policy-translator/policy_translator.py " + ' '.join([
            "--csv", "--out", REACH, ROLES, POLICY
        ])
    )

    os.system(
        "python2 bench/wl_stanford/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH, '-c', CHECKS
        ])
    )

    routes = []
    portmap = {}
    port_to_name = {}
    active_egress_ports = {}
    active_ingress_ports = {}
    active_link_ports = set()
    table_from_id = {}
    ext_ports = {}

    links = []

    routers = json.load(open('bench/wl_stanford/stanford-json/devices.json', 'r'))

    os.system("python2 bench/wl_stanford/topology_to_json.py bench/wl_stanford/stanford-tfs/topology.tf")

    for tf, t in [('bench/wl_stanford/stanford-tfs/%s.tf' % r, t) for r, t in routers.iteritems()]:
        os.system("python2 bench/wl_stanford/tf_to_json.py %s %s" % (tf, t))


    for tf in ['bench/wl_stanford/stanford-json/%s.tf.json' % r for r in routers]:
        with open(tf, 'r') as tf_f:
            name = tf.split('.')[0].split('/').pop()
            table = json.loads(tf_f.read())

            tid = table['id']
            table_from_id[tid] = name
            base_port = tid * 100000
            ext_port = tid * 100000 + 90000

            ext_ports[name] = ext_port
            table_ports = set(table['ports'] + [ext_port])

            portmap[name] = table_ports
            active_ingress_ports.setdefault(name, set())
            active_egress_ports.setdefault(name, set())

            for rule in table['rules']:
                active_ingress_ports[name].update([p for p in rule['in_ports'] if not (p == base_port or is_intermediate_port(p, base_port))])
                active_egress_ports[name].update([p for p in rule['out_ports'] if is_output_port(p, base_port)])

            portno = 1
            for port in table_ports:
                port_to_name[port] = "%s.%s" % (name, portno)
                portno += 1

            for rule in table['rules']:
                routes.append(rule_to_route(rule, base_port, ext_port))

            links.append((port_to_name[base_port], port_to_name[base_port], False))
            active_link_ports.add(base_port)
            for port in [
                p for p in table_ports if is_intermediate_port(p, base_port)
            ]:
                links.append((port_to_name[port], port_to_name[port], False))
                active_link_ports.add(port)


    with open (ROUTES, 'w') as rf:
        rf.write(json.dumps(routes, indent=2)+'\n')

    sources_links = []
    with open('bench/wl_stanford/stanford-json/topology.json', 'r') as tf:

        topo = json.load(tf)

        cnt = 1
        for link in topo['topology']:
            src = link['src']
            dst = link['dst']

            active_link_ports.add(src)
            active_link_ports.add(dst)

            if src not in port_to_name:
                rname = table_from_id[src / 100000]
                port_to_name[src] = "%s.%s" % (rname, len(portmap[rname]) + 1)
                portmap[rname].add(src)

            if dst not in port_to_name:
                rname = table_from_id[dst / 100000]
                port_to_name[dst] = "%s.%s" % (rname, len(portmap[rname]) + 1)
                portmap[rname].add(dst)

            active_egress_ports[table_from_id[src / 100000]].add(src)
            active_ingress_ports[table_from_id[dst / 100000]].add(dst)

            links.append((port_to_name[src], port_to_name[dst], False))


    devices = []
    devices.extend([(n, 'switch', len(p)) for n, p in portmap.iteritems()])
    devices.append(('probe.Internet', "probe", "universal", None, None, ['vlan=0'], None))

    sources = [('source.Internet', "generator", ["ipv4_dst=0.0.0.0/0"])]

    for name in routers:
        sources.append((
            "source.%s" % name, "generator", ["ipv4_dst=0.0.0.0/0"]
        ))

        sources_links.append(
            ("source.%s.1" % name, port_to_name[ext_ports[name]], True)
        )

        devices.append((
            "probe.%s" % name, "probe", "universal", None, None, ['vlan=0'], None
        ))

        links.extend([
            (
                port_to_name[port], "probe.%s.1" % name, False
            ) for port in active_egress_ports[name] - active_link_ports
        ])

    with open(TOPOLOGY, 'w') as tf:
        tf.write(
            json.dumps({'devices' : devices, 'links' : links}, indent=2) + '\n'
        )

    with open(SOURCES, 'w') as tf:
        tf.write(
            json.dumps({'devices' : sources, 'links' : sources_links}, indent=2) + '\n'
        )

#    import sys
#    sys.exit(0)

    os.system("bash scripts/start_np.sh bench/wl_ifi/np.conf 127.0.0.1 44001")
    os.system("bash scripts/start_aggr.sh 127.0.0.1:44001")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "create topology..."
        create_topology(devices, links)
        print "topology sent to fave"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        print "add routes..."
        add_routes(routes)
        print "routes sent to fave"

    with open(SOURCES, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "create sources..."
        create_topology(devices, links)
        print "sources sent to fave"

    print "wait for fave..."

    import netplumber.dump_np as dumper
    dumper.main(["-ans"])

    os.system("bash scripts/stop_fave.sh")

    import test.check_flows as checker
    checks = json.load(open(CHECKS, 'r'))
    checker.main(["-b", "-c", ";".join(checks)])


    os.system("rm -f np_dump/.lock")
