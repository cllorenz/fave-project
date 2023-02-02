#!/usr/bin/env python3

import sys
import json

with open(sys.argv[1], 'r') as f:
    tf = f.read().splitlines()

    tid = int(sys.argv[2])

    ports = set()
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
            print('not parseable:', line)
            continue

        rid = (tid << 32) + cnt

        if in_ports:
            in_ports = json.loads(in_ports)
            ports.update(in_ports)

        if out_ports:
            out_ports = json.loads(out_ports)
            ports.update(out_ports)

        rule = {
            'id' : rid,
            'action' : action,
            'in_ports' : in_ports,
            'out_ports' : out_ports,
            'match' : match.replace(',', '')
        }

        if mask != 'None':
            rule['mask'] = mask.replace(',', '')

        if rewrite != 'None':
            rule['rewrite'] = rewrite.replace(',', '')

        rules.append(rule)
        cnt += 1

    table['ports'] = list(ports)

    with open('/'.join(sys.argv[1].split('/')[:len(sys.argv[1].split('/'))-2] + ['i2-json', sys.argv[1].split('/')[len(sys.argv[1].split('/'))-1].split('.')[0]+'.tf.json']), 'w') as of:
        of.write(json.dumps(table, indent=2)+'\n')
