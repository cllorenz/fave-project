#!/usr/bin/env python2

import os
import json
import sys

src_dir = sys.argv[1]
dst_dir = sys.argv[2]

def toggle_mask_bits(mask):
    return mask.replace('0', 'x').replace('1', '0').replace('x', '1') if mask else mask

config_json = json.load(open("%s/config.json" % src_dir))

for tid, table in enumerate(config_json['tables'], start=1):
    print "table", table
    for ttid, ttype in enumerate(config_json['table_types']):
        etid = tid * 10 + ttid
        print "  ttype", ttype
        print "    read from", '%s/%s.tf.json' % (src_dir, etid)
        tab = json.load(open('%s/%s.tf.json' % (src_dir, etid)))

        assert etid == tab['id']
        tab['rules'].reverse()

        for rid, rule in enumerate(tab['rules'], start=0):
            rule['position'] = rid
            rule['id'] = (etid << 32) + rid + 1
            rule['mask'] = toggle_mask_bits(rule['mask'])

        print "    write to %s/%s.tf.json" % (dst_dir, etid)
        json.dump(tab, open('%s/%s.tf.json' % (dst_dir, etid), 'w'), indent=1)

os.system('cp %s/config.json %s/config.json' % (src_dir, dst_dir))
os.system('cp %s/topology.json %s/topology.json' % (src_dir, dst_dir))
os.system('cp %s/policy.json %s/policy.json' % (src_dir, dst_dir))
