#!/usr/bin/env python2

import sys
import json


with open(sys.argv[1], 'r') as f:
    topo = []

    topology = {
        'topology' : topo
    }

    tf = f.read().split('\n')

    for line in tf:
        try:
            _, src, _, _, _, _, _, dst, _, _, _, _, _, _ = line.split('$')
        except:
            print 'not parseable:', line
            continue

        src = int(src.strip('[]'))
        dst = int(dst.strip('[]'))

        topo.append({'src' : src, 'dst' : dst})


    with open('i2-hassel/topology.json', 'w') as of:
        of.write(json.dumps(topology, indent=2)+'\n')
