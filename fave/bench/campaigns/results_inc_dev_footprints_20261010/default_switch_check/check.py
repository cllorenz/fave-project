"""Scores EXPECTED.txt: the two switch-check cells against the campaign's cells."""
import gzip, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
def cell(*p):
    d = os.path.join(HERE, *p, 'rep01')
    head = json.load(open(os.path.join(d, 'head.json')))
    return head, [json.loads(l) for l in gzip.open(os.path.join(d, 'updates.jsonl.gz'), 'rt')]
C = 'wl_cloud_ndd-apkeep_s1'
_, old = cell('..', 'cells_default', C)
_, both = cell('..', 'cells_witness+dead-ends', C)
ok = True
for name, ref, fp, want in (('default', both, ['witness', 'dead-ends'], 10), ('coarse', old, [], 5330)):
    head, us = cell(name, C)
    tot = sum(u['rechecked'] for u in us)
    per = [u['rechecked'] for u in us] == [u['rechecked'] for u in ref]
    verd = len(us) == len(old) and all(sorted(map(str, a['changed'])) == sorted(map(str, b['changed']))
                                       for a, b in zip(us, old))
    good = head['footprint'] == fp and tot == want and per and verd
    ok &= good
    print('%-8s footprint=%s re-checked=%d (want %d) per-update equal=%s verdicts equal=%s -> %s'
          % (name, head['footprint'], tot, want, per, verd, 'held' if good else 'FAILED'))
print('all held' if ok else 'NOT all held')
