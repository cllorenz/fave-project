#!/usr/bin/env python2

import sys
import json


with open(sys.argv[1], 'r') as f:
    topo = []

    topology = {
        'topology' : topo
    }

    tf = f.read().splitlines()

    for line in [l for l in tf if l.startswith('link')]:
        _, src, _, _, _, _, _, dst, _, _, _, _, _, _ = line.split('$')

        src = int(src.strip('[]'))-20000
        dst = int(dst.strip('[]'))

        topo.append({'src' : src, 'dst' : dst})


    with open('/'.join(sys.argv[1].split('/')[:len(sys.argv[1].split('/'))-2] + ['i2-json', 'topology.json']), 'w') as of:
        of.write(json.dumps(topology, indent=2)+'\n')
