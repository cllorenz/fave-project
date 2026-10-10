"""P2: the oracle runs -- no sample mismatch after any update; at every checkpoint
selective == full and full == from-zero (empty mismatch lists)."""
import gzip, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
for w in ('wl_ifi', 'wl_airtel1', 'wl_cloud'):
    rs = [json.loads(l) for l in gzip.open(os.path.join(HERE, 'oracle', '%s_ndd-apkeep_s2' % w, 'rep01', 'oracle.jsonl.gz'), 'rt')]
    cps = [r for r in rs if 'full' in r]
    print(w, 'updates', len(rs), 'sample mismatches', sum(len(r['sample_mismatch']) for r in rs),
          'checkpoints', len(cps), 'selective != full', sum(len(r['selective_vs_full']) for r in cps),
          'full != from-zero', sum(len(r['full_vs_zero']) for r in cps))
