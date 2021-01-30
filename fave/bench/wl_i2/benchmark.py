#!/usr/bin/env python2

import os
import re
import json
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import Vector
from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies

ROLES='bench/wl_i2/roles.txt'
POLICY='bench/wl_i2/reach.txt'
REACH='bench/wl_i2/reach.csv'

CHECKS='bench/wl_i2/checks.json'

TOPOLOGY='bench/wl_i2/i2-json/topology.json'
ROUTES='bench/wl_i2/i2-json/routes.json'
SOURCES='bench/wl_i2/i2-json/sources.json'

with open('bench/wl_i2/i2-json/mapping.json', 'r') as mf:
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

    match = rule['match']
    start, end = get_start_end('packet.ipv4.destination')
    if match[start:end] != 'x'*FIELD_SIZES['packet.ipv4.destination']:
        dst = "ipv4_dst=%s" % array_ipv4_to_cidr(match[start:end])
        match_fields.append(dst)

    start, end = get_start_end('packet.ether.vlan')
    if match[start:end] != 'x'*FIELD_SIZES['packet.ether.vlan']:
        vlan = "vlan=%s" % array_vlan_to_number(match[start:end])
        match_fields.append(vlan)

    actions = []

    if rule['action'] == 'rw':
        mask = rule['mask']
        rewrite = rule['rewrite']

        fields = []

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

        if fields != []:
            actions.append("rw=%s" % ';'.join(fields))

    actions.extend(["fd=%s" % port_to_name[p] for p in out_ports])

    return (
        name, 1, rid, match_fields, actions,
        [port_to_name[p] for p in in_ports]
    )


if __name__ == '__main__':
    os.system("mkdir -p /tmp/np")
    os.system("rm -rf /tmp/np/*.log")

    os.system(
        "python2 ../policy-translator/policy_translator.py " + ' '.join([
            "--csv", "--out", REACH, ROLES, POLICY
        ])
    )

    os.system(
        "python2 bench/wl_i2/reach_csv_to_checks.py " + ' '.join([
            '-p', REACH, '-c', CHECKS
        ])
    )

    routes = []
    portmap = {}
    port_to_name = {}
    active_egress_ports = {}
    active_ingress_ports = {}
    active_link_ports = set()

    routers = json.load(open('bench/wl_i2/i2-json/devices.json', 'r'))

    os.system("python2 bench/wl_i2/topology_to_json.py bench/wl_i2/i2-hassel/backbone_topology.tf")

    for tf, t in [('bench/wl_i2/i2-hassel/%s.tf' % r, t) for r, t in routers.iteritems()]:
        os.system("python2 bench/wl_i2/tf_to_json.py %s %s" % (tf, t))

    for tf in ['bench/wl_i2/i2-json/%s.tf.json' % r for r in routers]:
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
                    portno += 1

            for rule in table['rules']:
                routes.append(rule_to_route(rule))


    with open (ROUTES, 'w') as rf:
        rf.write(json.dumps(routes, indent=2)+'\n')


    devices = []
    devices.extend([(n, 'switch', 64) for n in portmap])
    devices.append(('probe.Internet', "probe", "universal", None, None, ['vlan=0'], None))

    sources = [('source.Internet', "generator", ["ipv4_dst=0.0.0.0/0"])]

    links = []
    sources_links = []
    with open('bench/wl_i2/i2-json/topology.json', 'r') as tf:

        topo = json.load(tf)

        cnt = 1
        for link in topo['topology']:
            is_src = is_dst = False

            src = link['src']
            dst = link['dst']

            active_link_ports.add(src)
            active_link_ports.add(dst)

            links.append((port_to_name[src], port_to_name[dst]))


    for name in ['atla', 'chic', 'hous', 'kans', 'losa', 'newy32aoa', 'salt', 'seat', 'wash']:
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

    os.system("bash scripts/start_np.sh bench/wl_i2/np.conf")
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
    dumper.main(["-ant"])

    os.system("bash scripts/stop_fave.sh")

#    os.system("python2 misc/await_fave.py")

    import test.check_flows as checker
    checks = json.load(open(CHECKS, 'r'))
    checker.main(["-b", "-c", ";".join(checks)])


    os.system("rm -f np_dump/.lock")


#    os.system("net_plumber --hdr-len 6 --load bench/wl_internet2")
