"""VeriFlow-FR's footprint modes against coarse, per (workload, stream): re-checks
summed (check lines), their change against coarse, verdict changes equal to
coarse's on every update, medians of t_update, t_recheck and t_total (ms). Then
PROTOCOL.txt's predictions, scored from the same numbers, and the oracle runs.
Generated output: compare.md (python3 compare.py > compare.md)."""
import gzip, json, os, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
MODES = ('coarse', 'witness', 'dead-ends', 'witness+dead-ends')
WLS = ('wl_example', 'wl_ifi', 'wl_airtel1', 'wl_cloud')
STREAMS = ('s1', 's2', 's3')


def load(mode, w, s):
    p = os.path.join(HERE, 'cells_' + mode, '%s_veriflow_%s' % (w, s), 'rep01', 'updates.jsonl.gz')
    return [json.loads(l) for l in gzip.open(p, 'rt')] if os.path.exists(p) else None


def med(us, f):
    return 1000 * statistics.median(f(u) for u in us)


R = {}
print('| workload | stream | mode | re-checked | vs coarse | verdicts = coarse | t_update med ms | t_recheck med ms | t_total med ms |')
print('|---|---|---|---:|---:|---|---:|---:|---:|')
for w in WLS:
    for s in STREAMS:
        base = load('coarse', w, s)
        for m in MODES:
            us = load(m, w, s)
            if us is None or base is None:
                print('| %s | %s | %s | missing | | | | | |' % (w, s, m))
                continue
            same = len(us) == len(base) and all(
                sorted(map(str, a['changed'])) == sorted(map(str, b['changed']))
                for a, b in zip(us, base))
            tot, b0 = sum(u['rechecked'] for u in us), sum(u['rechecked'] for u in base)
            tu = med(us, lambda u: u['t_update_s'])
            rc = med(us, lambda u: u['t_recheck_s'])
            tt = med(us, lambda u: u['t_update_s'] + u['t_recheck_s'])
            R[(w, s, m)] = dict(tot=tot, same=same, tu=tu, rc=rc, tt=tt, n=len(us))
            vs = '' if m == 'coarse' else ('%+.0f%%' % (100.0 * (tot - b0) / b0) if b0 else 'n/a')
            print('| %s | %s | %s | %d | %s | %s | %.2f | %.2f | %.2f |' % (
                w, s, m, tot, vs, same, tu, rc, tt))


def get(w, s, m):
    return R.get((w, s, m))


def pct(w, s, m):
    a, b = get(w, s, m), get(w, s, 'coarse')
    return a['tot'] / b['tot'] if a and b and b['tot'] else float('nan')


print()
print('## Predictions')
print()
both = 'witness+dead-ends'
p1 = all(r['same'] for r in R.values())
print('- P1 every mode changes the same verdicts as coarse on every update: **%s**' % ('held' if p1 else 'FALSIFIED: ' + ', '.join('%s %s %s' % k for k, r in R.items() if not r['same'])))
oracle = []
for w in ('wl_ifi', 'wl_airtel1', 'wl_cloud'):
    p = os.path.join(HERE, 'oracle', '%s_veriflow_s2' % w, 'rep01', 'oracle.jsonl.gz')
    if not os.path.exists(p):
        oracle.append((w, 'missing'))
        continue
    recs = [json.loads(l) for l in gzip.open(p, 'rt')]
    bad = [r for r in recs if r['sample_mismatch'] or r.get('selective_vs_full') or r.get('full_vs_zero')]
    full = sum(1 for r in recs if r.get('full'))
    oracle.append((w, 'pass (%d records, %d full checkpoints)' % (len(recs), full) if not bad else 'FAIL at b=%d' % bad[0]['b']))
p2 = all(v.startswith('pass') for _w, v in oracle)
print('- P2 the three oracle runs pass: **%s** -- %s' % ('held' if p2 else 'FALSIFIED', '; '.join('%s %s' % o for o in oracle)))
p3 = [(w, s) for w in WLS for s in STREAMS if get(w, s, both) and get(w, s, both)['tot'] > get(w, s, 'coarse')['tot']]
print('- P3 both <= coarse re-checks on every stream: **%s**' % ('held' if not p3 else 'FALSIFIED on %s' % p3))
p4 = [(s, pct('wl_airtel1', s, both), get('wl_airtel1', s, both)['rc'] / get('wl_airtel1', s, 'coarse')['rc']) for s in ('s1', 's2')]
print('- P4 wl_airtel1 S1/S2 both: re-checks <= 1%%, median t_recheck <= 10%% of coarse: **%s** -- %s' % (
    'held' if all(a <= 0.01 and b <= 0.10 for _s, a, b in p4) else 'FALSIFIED',
    '; '.join('%s re-checks %.2f%%, t_recheck %.1f%%' % (s, 100 * a, 100 * b) for s, a, b in p4)))
p5 = [(s, pct('wl_ifi', s, both)) for s in ('s1', 's2')]
print('- P5 wl_ifi S1/S2 both: re-checks <= 40%% of coarse: **%s** -- %s' % (
    'held' if all(a <= 0.40 for _s, a in p5) else 'FALSIFIED', '; '.join('%s %.0f%%' % (s, 100 * a) for s, a in p5)))
p6 = 1 - pct('wl_airtel1', 's3', 'witness')
print('- P6 wl_airtel1 S3 witness alone: >= 30%% below coarse: **%s** -- %.0f%% below' % ('held' if p6 >= 0.30 else 'FALSIFIED', 100 * p6))
p7 = [(w, s, get(w, s, both)['tu'] / get(w, s, 'coarse')['tu']) for w in WLS for s in STREAMS if get(w, s, both)]
worst = max(p7, key=lambda x: x[2])
print('- P7 both: median t_update <= 3x coarse on every stream: **%s** -- worst %s %s %.2fx' % (
    'held' if all(r <= 3 for _w, _s, r in p7) else 'FALSIFIED on %s' % [(w, s, round(r, 2)) for w, s, r in p7 if r > 3], worst[0], worst[1], worst[2]))
p8 = [(s, get('wl_airtel1', s, both)['tt'], get('wl_airtel1', s, 'coarse')['tt']) for s in ('s1', 's2')]
print('- P8 wl_airtel1 S1/S2 both: median t_total below coarse: **%s** -- %s' % (
    'held' if all(a < b for _s, a, b in p8) else 'FALSIFIED', '; '.join('%s %.2f vs %.2f ms' % x for x in p8)))
p9 = pct('wl_ifi', 's1', 'dead-ends')
print('- P9 wl_ifi S1 dead-ends alone: <= 70%% of coarse: **%s** -- %.0f%%' % ('held' if p9 <= 0.70 else 'FALSIFIED', 100 * p9))
