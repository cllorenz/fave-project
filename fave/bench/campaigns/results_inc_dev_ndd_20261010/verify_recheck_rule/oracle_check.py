"""The F variant's oracle cells: every sampled check matches after each update, and at
each checkpoint selective == full and full == from-zero."""
import gzip, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
for w in ('wl_ifi', 'wl_airtel1', 'wl_cloud'):
    rs = [json.loads(l) for l in gzip.open('%s/oracle/%s_ndd-apkeep_s2/rep01/oracle.jsonl.gz' % (HERE, w), 'rt')]
    mism = sum(len(r['sample_mismatch']) for r in rs)
    cps = [r for r in rs if 'full' in r]
    print(w, 'updates', len(rs), 'sample mismatches', mism, 'checkpoints', len(cps),
          'selective==full', all(r['selective_vs_full'] in (True, [], {}, 0) for r in cps), set(map(str, (r['selective_vs_full'] for r in cps))),
          'full==zero', set(map(str, (r['full_vs_zero'] for r in cps))))
