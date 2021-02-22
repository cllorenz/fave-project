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


def _generic_port_check(port, offset, base):
    return port - offset > base and port  - 2  * offset < base

def _is_intermediate_port(port, base):
    return _generic_port_check(port, 10000, base)

def _is_output_port(port, base):
    return _generic_port_check(port, 20000, base)


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
    if not any([_is_intermediate_port(p, base_port) for p in in_ports]):
        in_ports.append(ext_port)
    out_ports = rule['out_ports']

    match_fields = []

    match = rule['match']

    dst = _get_field_from_match(
        match, 'packet.ipv4.destination', 'ipv4_dst', array_ipv4_to_cidr
    )
    if dst: match_fields.append(dst)

    vlan = _get_field_from_match(
        match, 'packet.ether.vlan', 'vlan', array_vlan_to_number
    )
    if vlan: match_fields.append(vlan)

    actions = []

    if rule['action'] == 'rw':
        mask = rule['mask']
        rewrite = rule['rewrite']

        fields = []

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
    table_from_id = {}
    ext_ports = {}

    links = []

    routers = json.load(open('bench/wl_i2/i2-json/devices.json', 'r'))

    os.system("python2 bench/wl_i2/topology_to_json.py bench/wl_i2/i2-tfs/backbone_topology.tf")

    for tf, t in [('bench/wl_i2/i2-tfs/%s.tf' % r, t) for r, t in routers.iteritems()]:
        os.system("python2 bench/wl_i2/tf_to_json.py %s %s" % (tf, t))

    for tf in ['bench/wl_i2/i2-json/%s.tf.json' % r for r in routers]:
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
                active_ingress_ports[name].update([p for p in rule['in_ports'] if not (p == base_port or _is_intermediate_port(p, base_port))])
                active_egress_ports[name].update([p for p in rule['out_ports'] if _is_output_port(p, base_port)])

            portno = 1
            for port in table_ports:
                port_to_name[port] = "%s.%s" % (name, portno)
                portno += 1

            for rule in table['rules']:
                routes.append(rule_to_route(rule, base_port, ext_port))

            links.append((port_to_name[base_port], port_to_name[base_port]))
            active_link_ports.add(base_port)
            for port in [
                p for p in table_ports if _is_intermediate_port(p, base_port)
            ]:
                links.append((port_to_name[port], port_to_name[port]))
                active_link_ports.add(port)


    with open (ROUTES, 'w') as rf:
        rf.write(json.dumps(routes, indent=2)+'\n')


    with open('bench/wl_i2/i2-json/topology.json', 'r') as tf:

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

            links.append((port_to_name[src], port_to_name[dst]))


    devices = []
    devices.extend([(n, 'switch', len(p)) for n, p in portmap.iteritems()])
    devices.append(('probe.Internet', "probe", "universal", None, None, ['vlan=0'], None))

    sources = [('source.Internet', "generator", ["ipv4_dst=0.0.0.0/0"])]


    sources_links = []
    for name in routers:
        sources.append((
            "source.%s" % name, "generator", ["ipv4_dst=0.0.0.0/0"]
        ))

        sources_links.append(
            ("source.%s.1" % name, port_to_name[ext_ports[name]])
        )

        devices.append((
            "probe.%s" % name, "probe", "universal", None, None, ['vlan=0'], None
        ))

        links.extend([
            (
                port_to_name[port], "probe.%s.1" % name
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

    os.system("bash scripts/start_np.sh bench/wl_i2/np.conf")
    os.system("bash scripts/start_aggr.sh")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "initialize topology..."
        create_topology(devices, links)
        print "topology sent to fave"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        print "initialize routes..."
        add_routes(routes)
        print "routes sent to fave"

    with open(SOURCES, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "initialize sources..."
        create_topology(devices, links)
        print "sources sent to fave"

    print "wait for fave..."

    import netplumber.dump_np as dumper
    dumper.main(["-ant"])

    os.system("bash scripts/stop_fave.sh")

    import test.check_flows as checker
    checks = json.load(open(CHECKS, 'r'))
    checker.main(["-b", "-c", ";".join(checks)])

    os.system("rm -f np_dump/.lock")
