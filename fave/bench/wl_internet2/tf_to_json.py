#!/usr/bin/env python2

import sys
import json

with open(sys.argv[1], 'r') as f:
    tf = f.read().split('\n')

    tid = int(tf[0].split('$')[2])
    tf = tf[1:]

    ports = set()
    rules = []

    table = {
        'id' : tid,
        'rules' : rules
    }

    cnt = 1
    for line in tf:
        if line == "" or line.startswith('#'):
            continue

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

    with open(str(tid)+'.tf.json', 'w') as of:
        of.write(json.dumps(table))
