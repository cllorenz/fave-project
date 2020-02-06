#!/usr/bin/env python2

import os
import re
import json
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import Vector
from bench.bench_utils import create_topology, add_rulesets, add_routes, add_policies


TOPOLOGY='bench/wl_i2/i2-hassel/topology.json'
ROUTES='bench/wl_i2/i2-hassel/routes.json'

with open('bench/wl_i2/i2-hassel/mapping.json', 'r') as mf:
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
        raise "array not a vlan number: %s" % array


def get_start_end(field):
    start = MAPPING[field]
    end = start + FIELD_SIZES[field]
    return start, end


def rule_to_route(rule):
    rid = int(rule['id']) & 0xffff

    in_ports = rule['in_ports']
    out_ports = rule['out_ports']

    match = rule['match']
    start, end = get_start_end('packet.ipv4.destination')
    dst = "ipv4_dst=%s" % array_ipv4_to_cidr(match[start:end])

    start, end = get_start_end('packet.ether.vlan')
    vlan = "vlan=%s" % array_vlan_to_number(match[start:end])

    actions = []

    if rule['action'] == 'rw':
        mask = rule['mask']
        rewrite = rule['rewrite']

        fields = []

        start, end = get_start_end('packet.ipv4.destination')
        field_mask = mask[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.ipv4.destination']:
            fields.append("ipv4_dst:%s" % array_ipv4_to_cidr(rewrite[start:end]))

        start, end = get_start_end('packet.ether.vlan')
        field_mask = mask[start:end]
        if field_mask == '1'*FIELD_SIZES['packet.ether.vlan']:
            fields.append("vlan:%s" % array_vlan_to_number(rewrite[start:end]))

        actions.append("rw=%s" % ';'.join(fields))

    actions.extend(["fd=%s" % port_to_name[p] for p in out_ports])

    return (
        name, 1, rid, [dst, vlan], actions,
        [port_to_name[p] for p in in_ports]
    )


if __name__ == '__main__':
    routes = []
    portmap = {}
    port_to_name = {}

    files = [
        'bench/wl_i2/i2-hassel/atla.tf.json',
        'bench/wl_i2/i2-hassel/chic.tf.json',
        'bench/wl_i2/i2-hassel/kans.tf.json',
        'bench/wl_i2/i2-hassel/salt.tf.json',
        'bench/wl_i2/i2-hassel/hous.tf.json',
        'bench/wl_i2/i2-hassel/losa.tf.json',
        'bench/wl_i2/i2-hassel/newy32aoa.tf.json',
        'bench/wl_i2/i2-hassel/seat.tf.json',
        'bench/wl_i2/i2-hassel/wash.tf.json'
    ]
    for tf in files:
        with open(tf, 'r') as tf_f:
            name = tf.split('.')[0].split('/').pop()
            table = json.loads(tf_f.read())

            portmap[name] = set()

            for rule in table['rules']:
                portmap[name].update(rule['in_ports'])
                portmap[name].update(rule['out_ports'])

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

    links = []
    with open('bench/wl_i2/i2-hassel/topology.tf', 'r') as tf:
        active_ports = set()

        cnt = 1
        for line in tf.read().split('\n'):
            is_src = is_dst = False

            try:
                _, src, _, _, _, _, _, dst, _, _, _, _, _, _ = line.split('$')
            except:
                continue

            src = int(src.strip('[]'))
            dst = int(dst.strip('[]'))

            if src not in port_to_name:
                port_to_name[src] = 'source.external.%s.1' % cnt
                is_src = True
            if dst not in port_to_name:
                port_to_name[dst] = 'probe.external.%s.1' % cnt
                is_dst = True
                continue # XXX

            if not is_src:
                active_ports.add(src)
            if not is_dst:
                active_ports.add(dst)

            if is_src:
                devices.append(
                    ("source.external.%s" % cnt, "generator", ["ipv4_dst=0.0.0.0/0"])
                )
                cnt += 1
            elif is_dst:
#                devices.append(("probe.external.%s" % cnt, "probe", "universal", None, None, []))
                cnt += 1

            links.append((port_to_name[src], port_to_name[dst]))

        for port in active_ports:
            pname = port_to_name[port]
            devices.append((
                "source.%s" % pname, "generator", ["ipv4_dst=0.0.0.0/0"]
            ))
            links.append(("source.%s.1" % pname, pname))

    with open('bench/wl_i2/i2-hassel/topology.json', 'w') as tf:
        tf.write(
            json.dumps({'devices' : devices, 'links' : links}, indent=2) + '\n'
        )


    os.system("bash scripts/start_np.sh bench/wl_i2/np.conf")
    os.system("bash scripts/start_aggr.sh")

    with open(TOPOLOGY, 'r') as raw_topology:
        devices, links = json.loads(raw_topology.read()).values()

        print "create topology... ",
        create_topology(devices, links)
#        add_rulesets(devices)
        print "done"

    with open(ROUTES, 'r') as raw_routes:
        routes = json.loads(raw_routes.read())

        print "add routes... ",
        add_routes(routes)
        print "done"

    import netplumber.dump_np as dumper
#    import test.check_flows as checker

    dumper.main(["-anpft"])
#    checker.main(["-c", ";".join(checks)])

    os.system("bash scripts/stop_fave.sh")
    os.system("rm -f np_dump/.lock")


#    os.system("net_plumber --hdr-len 6 --load bench/wl_internet2")
