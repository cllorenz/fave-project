#!/usr/bin/env python2

import sys
import json

with open(sys.argv[1], 'r') as f:
    tf = f.read().splitlines()

    tid = int(sys.argv[2]) #int(tf[0].split('$')[2])
    base_port = tid * 100000
    #tf = tf[1:]

    ports = set()
    rules = []

    table = {
        'id' : tid,
        'rules' : rules
    }

    is_default = True
    default_rule = None

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
            ports.update(set([p for p in in_ports if p != base_port]))

        if out_ports:
            out_ports = json.loads(out_ports)
            ports.update(set([p-20000 for p in out_ports if p != base_port]))

        rule = {
            'id' : rid,
            'action' : action,
            'in_ports' : [p for p in in_ports if p != base_port],
            'out_ports' : [p-20000 for p in out_ports if p != base_port],
            'match' : match
        }

        if mask != 'None':
            rule['mask'] = mask

        if rewrite != 'None':
            rule['rewrite'] = rewrite

        if is_default:
            rule['id'] = (tid << 32) + len(tf) - 1
            default_rule = rule
            is_default = False
        else:
            rules.append(rule)
        cnt += 1

    rules.append(default_rule)

    table['ports'] = list(ports)

    with open('/'.join(sys.argv[1].split('/')[:len(sys.argv[1].split('/'))-2] + ['i2-tfs', sys.argv[1].split('/')[len(sys.argv[1].split('/'))-1].split('.')[0]+'.tf.json']), 'w') as of:
        of.write(json.dumps(table, indent=2)+'\n')
