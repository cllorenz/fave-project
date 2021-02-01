#!/usr/bin/env python2

import os
import re
import json
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import Vector
from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies

ROLES='bench/wl_stanford/roles.txt'
POLICY='bench/wl_stanford/reach.txt'
REACH='bench/wl_stanford/reach.csv'

CHECKS='bench/wl_stanford/checks.json'

TOPOLOGY='bench/wl_stanford/stanford-json/topology.json'
ROUTES='bench/wl_stanford/stanford-json/routes.json'
SOURCES='bench/wl_stanford/stanford-json/sources.json'

with open('bench/wl_stanford/stanford-json/mapping.json', 'r') as mf:
    MAPPING = Mapping.from_json(json.loads(mf.read()))


def array_ipv4_to_cidr(array):
    assert 32 == len(array)
    cidr_regex = '(?P<pre>[01]*)(?P<post>x*)'
    m = re.match(cidr_regex, array)
    if m and 32 == len(m.group('pre')) + len(m.group('post')):
        pre = m.group('pre')
        plen = len(pre)
        post = '0'*len(m.group('post'))

        octal_regex = '(?P<i1>[01]{8})(?P<i2>[01]{8})(?P<i3>[01]{8})(?P<i4>[01]{8})'
        o = re.match(octal_regex, pre+post)
        octals = "%s.%s.%s.%s" % (
            int(o.group('i1'), 2),
            int(o.group('i2'), 2),
            int(o.group('i3'), 2),
            int(o.group('i4'), 2)
        )

        return "%s/%s" % (octals, plen)
    else:
        raise Exception("array not in cidr format: %s" % array)


def array_vlan_to_number(array):
    assert 16 == len(array)
    if 'x'*16 == array:
        return 0

    vlan_regex = '((xxxx)|(0000))(?P<vlan>[01]{12})'
    m = re.match(vlan_regex, array)
    if m:
        return int(m.group('vlan'), 2)
    else:
        raise Exception("array not a vlan number: %s" % array)


def get_start_end(field):
    start = MAPPING[field]
    end = start + FIELD_SIZES[field]
    return start, end


def rule_to_route(rule):
    rid = int(rule['id']) & 0xffff

    in_ports = rule['in_ports']
    out_ports = rule['out_ports']

    match_fields = []

    match = rule['match'].replace(',', '')

    start, end = get_start_end('packet.ipv4.source')
    if match[start:end] != 'x'*FIELD_SIZES['packet.ipv4.source']:
        src = "ipv4_src=%s" % array_ipv4_to_cidr(match[start:end])
        match_fields.append(src)

    start, end = get_start_end('packet.ipv4.destination')
    if match[start:end] != 'x'*FIELD_SIZES['packet.ipv4.destination']:
        dst = "ipv4_dst=%s" % array_ipv4_to_cidr(match[start:end])
        match_fields.append(dst)

    start, end = get_start_end('packet.ether.vlan')
    if match[start:end] != 'x'*FIELD_SIZES['packet.ether.vlan']:
        vlan = "vlan=%s" % array_vlan_to_number(match[start:end])
        match_fields.append(vlan)

    start, end = get_start_end('packet.ipv6.proto')
    if match[start:end] != 'x'*FIELD_SIZES['packet.ipv6.proto']:
        proto = "ip_proto=%s" % int(match[start:end], 2)
        match_fields.append(proto)

    start, end = get_start_end('packet.upper.sport')
    if match[start:end] != 'x'*FIELD_SIZES['packet.upper.sport']:
        try:
            sport = "tcp_src=%s" % int(match[start:end], 2)
        except ValueError:
            sport = "tcp_src=%s" % match[start:end]
        match_fields.append(sport)

    start, end = get_start_end('packet.upper.dport')
    if match[start:end] != 'x'*FIELD_SIZES['packet.upper.dport']:
        try:
            dport = "tcp_dst=%s" % int(match[start:end], 2)
        except ValueError:
            dport = "tcp_dst=%s" % match[start:end]
        match_fields.append(dport)

    start, end = get_start_end('packet.upper.tcp.flags')
    if match[start:end] != 'x'*FIELD_SIZES['packet.upper.tcp.flags']:
        try:
            flags = "tcp_flags=%s" % int(match[start:end], 2)
        except ValueError:
            flags = "tcp_flags=%s" % match[start:end]
        match_fields.append(flags)

    actions = []

    if rule['action'] == 'rw':
        mask = rule['mask'].replace(',', '')
        rewrite = rule['rewrite'].replace(',', '')

        fields = []

        start, end = get_start_end('packet.ipv4.source')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.ipv4.source'] and field_rewrite != '0'*FIELD_SIZES['packet.ipv4.source']:
            fields.append("ipv4_src:%s" % array_ipv4_to_cidr(rewrite[start:end]))

        start, end = get_start_end('packet.ipv4.destination')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.ipv4.destination'] and field_rewrite != '0'*FIELD_SIZES['packet.ipv4.destination']:
            fields.append("ipv4_dst:%s" % array_ipv4_to_cidr(rewrite[start:end]))

        start, end = get_start_end('packet.ether.vlan')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.ether.vlan'] and field_rewrite == '0'*FIELD_SIZES['packet.ether.vlan']:
            fields.append("vlan:%s" % array_vlan_to_number(rewrite[start:end]))

        start, end = get_start_end('packet.ipv6.proto')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.ipv6.proto'] and field_rewrite != '0'*FIELD_SIZES['packet.ipv6.proto']:
            fields.append("ip_proto:%s" % int(rewrite[start:end], 2))

        start, end = get_start_end('packet.upper.sport')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.upper.sport'] and field_rewrite != '0'*FIELD_SIZES['packet.upper.sport']:
            fields.append("tcp_src:%s" % int(rewrite[start:end], 2))

        start, end = get_start_end('packet.upper.dport')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.upper.dport'] and field_rewrite != '0'*FIELD_SIZES['packet.upper.dport']:
            fields.append("tcp_dst:%s" % int(rewrite[start:end], 2))

        start, end = get_start_end('packet.upper.tcp.flags')
        field_mask = mask[start:end]
        field_rewrite = rewrite[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.upper.tcp.flags'] and field_rewrite != '0'*FIELD_SIZES['packet.upper.tcp.flags']:
            fields.append("tcp_flags:%s" % int(rewrite[start:end], 2))

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
    os.system("mkdir -p /tmp/np")
    os.system("rm -rf /tmp/np/*.log")

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
    router_ports = {}
    active_egress_ports = {}
    active_ingress_ports = {}
    active_link_ports = set()

    routers = json.load(open('bench/wl_stanford/stanford-json/devices.json', 'r'))

    os.system("python2 bench/wl_stanford/topology_to_json.py bench/wl_stanford/stanford-tfs/topology.tf")

    for tf, t in [('bench/wl_stanford/stanford-tfs/%s.tf' % r, t) for r, t in routers.iteritems()]:
        os.system("python2 bench/wl_stanford/tf_to_json.py %s %s" % (tf, t))


    for tf in ['bench/wl_stanford/stanford-json/%s.tf.json' % r for r in routers]:
        with open(tf, 'r') as tf_f:
            name = tf.split('.')[0].split('/').pop()
            table = json.loads(tf_f.read())

            portmap[name] = set()
            active_ingress_ports.setdefault(name, set())
            active_egress_ports.setdefault(name, set())

            for rule in table['rules']:
                portmap[name].update(rule['in_ports'])
                active_ingress_ports[name].update(rule['in_ports'])
                portmap[name].update(rule['out_ports'])
                active_egress_ports[name].update(rule['out_ports'])

            for tname, ports in portmap.iteritems():
                portno = 1
                for port in ports:
                    port_to_name[port] = "%s.%s" % (tname, portno)
                    router_ports[name] = portno
                    portno += 1

            for rule in table['rules']:
                routes.append(rule_to_route(rule))


    with open (ROUTES, 'w') as rf:
        rf.write(json.dumps(routes, indent=2)+'\n')

    devices = []
    devices.extend([(n, 'switch', 192) for n in portmap])
    devices.append(('probe.Internet', "probe", "universal", None, None, ['vlan=0'], None))

    sources = [('source.Internet', "generator", ["ipv4_dst=0.0.0.0/0"])]

    hassel_port_map = _read_port_map('bench/wl_stanford/stanford-hassel/port_map.txt')

    links = []
    sources_links = []
    with open('bench/wl_stanford/stanford-json/topology.json', 'r') as tf:

        topo = json.load(tf)

        cnt = 1
        for link in topo['topology']:
            is_src = is_dst = False

            src = link['src']
            dst = link['dst']

            active_link_ports.add(src)
            active_link_ports.add(dst)

            if src not in port_to_name:
                rname = hassel_port_map[src]
                port_to_name[src] = "%s.%s" % (rname, router_ports[rname])
                router_ports[rname] += 1

            if dst not in port_to_name:
                rname = hassel_port_map[dst]
                port_to_name[dst] = "%s.%s" % (rname, router_ports[rname])
                router_ports[rname] += 1

            try:
                links.append((port_to_name[src], port_to_name[dst]))
            except KeyError:
                import pprint
                pprint.pprint(port_to_name, indent=2)
                raise


    for name in routers:
        sources.append((
            "source.%s" % name, "generator", ["ipv4_dst=0.0.0.0/0"]
        ))
        sources_links.extend([
            (
                "source.%s.1" % name, port_to_name[port]
            ) for port in active_ingress_ports[name] if port not in active_link_ports
        ])

        devices.append((
            "probe.%s" % name, "probe", "universal", None, None, ['vlan=0'], None
        ))

        links.extend([
            (
                port_to_name[port], "probe.%s.1" % name
            ) for port in active_egress_ports[name] if port not in active_link_ports
        ])

    with open(TOPOLOGY, 'w') as tf:
        tf.write(
            json.dumps({'devices' : devices, 'links' : links}, indent=2) + '\n'
        )

    with open(SOURCES, 'w') as tf:
        tf.write(
            json.dumps({'devices' : sources, 'links' : sources_links}, indent=2) + '\n'
        )

    os.system("bash scripts/start_np.sh bench/wl_stanford/np.conf")
    os.system("bash scripts/start_aggr.sh")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "create topology... ",
        create_topology(devices, links)
        print "done"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        print "add routes... ",
        add_routes(routes)
        print "done"

    with open(SOURCES, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "create sources... ",
        create_topology(devices, links)
        print "done"

    import netplumber.dump_np as dumper
    dumper.main(["-ans"])

    os.system("bash scripts/stop_fave.sh")

    import test.check_flows as checker
    checks = json.load(open(CHECKS, 'r'))
    checker.main(["-b", "-c", ";".join(checks)])


    os.system("rm -f np_dump/.lock")
