#!/usr/bin/env python2

import sys
import json


def _adjust_port(port, offset, base):
    if port - offset < base:
        return port
    else:
        return port - offset


def _generic_port_check(port, offset, base):
    return port - offset > base and port - 2 * offset < base

def _is_intermediate_port(port, base):
    return _generic_port_check(port, 10000, base)

def _is_output_port(port, base):
    return _generic_port_check(port, 20000, base)

with open(sys.argv[1], 'r') as f:
    tf = f.read().splitlines()

    tid = int(sys.argv[2])
    base_port = tid * 100000

    ports = set([base_port])
    rules = []

    table = {
        'id' : tid,
        'rules' : rules
    }

    cnt = 1
    for line in [l.rstrip() for l in tf if l.startswith('fwd') or l.startswith('rw')]:
        try:
            action, in_ports, match, mask, rewrite, _, _, out_ports, _, _, _, _, name, _ = line.split('$')
        except:
            print 'not parseable:', line
            continue

        rid = (tid << 32) + cnt

        if in_ports:
            in_ports = json.loads(in_ports)
            ports.update(set(in_ports))

        if out_ports:
            out_ports = json.loads(out_ports)
            ports.update(set(out_ports))

        rule = {
            'id' : rid,
            'action' : action,
            'in_ports' : in_ports,
            'out_ports' : out_ports,
            'match' : match
        }

        if mask != 'None':
            rule['mask'] = mask

        if rewrite != 'None':
            rule['rewrite'] = rewrite

        rules.append(rule)
        cnt += 1

    table['ports'] = list(ports)

    with open('/'.join(sys.argv[1].split('/')[:len(sys.argv[1].split('/'))-2] + ['stanford-json', sys.argv[1].split('/')[len(sys.argv[1].split('/'))-1].split('.')[0]+'.tf.json']), 'w') as of:
        of.write(json.dumps(table, indent=2)+'\n')
