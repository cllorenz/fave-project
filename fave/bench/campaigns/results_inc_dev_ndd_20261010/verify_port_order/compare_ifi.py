"""Per update, where the hash-order NDD-APKeep and BDD-APKeep re-check sets differ on wl_ifi S1/S2."""
import gzip, json, os
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cells')
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cells')
L = lambda d: [json.loads(l) for l in gzip.open(d + '/rep01/updates.jsonl.gz', 'rt')]
for s in ('s1', 's2'):
    for x, y in zip(L('%s/wl_ifi_apkeep_%s' % (R, s)), L('%s/wl_ifi_%s' % (S, s))):
        kb, kh = set(map(tuple, x['affected'])), set(map(tuple, y['affected']))
        if kb != kh:
            print(s, 'pos', x['pos'], x['ops'], 'bdd', len(kb), 'ndd', len(kh),
                  'only-bdd', len(kb - kh), 'only-ndd', len(kh - kb))
