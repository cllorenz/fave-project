import gzip, json, sys, os
R = '/home/ubuntu/fave-project/fave/bench/campaigns/results_inc_dev_ndd_20261010/cells'
S = os.path.dirname(os.path.abspath(__file__)) + '/cells'
def load(d):
    with gzip.open(d + '/rep01/updates.jsonl.gz', 'rt') as f:
        return [json.loads(l) for l in f]
print('%-14s %-4s %8s %8s %8s %6s %6s %6s' % ('workload', 's', 'bdd', 'ndd-old', 'ndd-hash', 'diff', 'diff', 'verd'))
print('%-14s %-4s %8s %8s %8s %6s %6s %6s' % ('', '', '', '', '', 'h~bdd', 'o~bdd', 'h=bdd'))
for w in ('wl_example', 'wl_airtel1', 'wl_ifi'):
    for s in ('s1', 's2', 's3'):
        try:
            b, o, h = load('%s/%s_apkeep_%s' % (R, w, s)), load('%s/%s_ndd-apkeep_%s' % (R, w, s)), load('%s/%s_%s' % (S, w, s))
        except OSError as ex:
            print(w, s, 'missing', ex); continue
        assert len(b) == len(o) == len(h), (len(b), len(o), len(h))
        key = lambda u: frozenset(map(tuple, u['affected']))
        dh = sum(key(x) != key(y) for x, y in zip(h, b))
        do = sum(key(x) != key(y) for x, y in zip(o, b))
        vc = all(sorted(map(str, x['changed'])) == sorted(map(str, y['changed'])) for x, y in zip(h, b))
        tot = lambda us: sum(u['rechecked'] for u in us)
        print('%-14s %-4s %8d %8d %8d %6d %6d %6s' % (w, s, tot(b), tot(o), tot(h), dh, do, vc))
