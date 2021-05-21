#!/usr/bin/env python2

import os
import json
import sys

src_dir = sys.argv[1]
dst_dir = sys.argv[2]

def toggle_mask_bits(mask):
    return mask.replace('0', 'x').replace('1', '0').replace('x', '1') if mask else mask

config_json = json.load(open("%s/config.json" % src_dir))
tables = {table : idx*10 for idx, table in enumerate(config_json["tables"], start=1)}

ttypes = { ttype : idx for idx, ttype in enumerate(config_json["table_types"]) }

for tid, table in enumerate(tables, start=1):
    print "table", table
    for ttid, ttype in enumerate(ttypes):
        print "  ttype", ttype
        print "    read from", '%s/%s.tf.json' % (src_dir, tid * 10 + ttid)
        tab = json.load(open('%s/%s.tf.json' % (src_dir, tid * 10 + ttid)))

        assert tid * 10 + ttid == tab['id']
        tab['rules'].reverse()

        for rid, rule in enumerate(tab['rules'], start=0):
            rule['position'] = rid
            rule['id'] = (tid << 32) + rid + 1
            rule['mask'] = toggle_mask_bits(rule['mask'])

        print "    write to %s/%s.tf.json" % (dst_dir, tid * 10 + ttid)
        json.dump(tab, open('%s/%s.tf.json' % (dst_dir, tid * 10 + ttid), 'w'), indent=1)

os.system('cp %s/config.json %s/config.json' % (src_dir, dst_dir))
os.system('cp %s/topology.json %s/topology.json' % (src_dir, dst_dir))
os.system('cp %s/policy.json %s/policy.json' % (src_dir, dst_dir))
