"""Footprint modes against the default, per (workload, engine, stream): re-checks
summed (check lines), their change against the default, verdict changes equal to
the default's on every update, medians of t_recheck and t_total (ms). Then the
protocol's predictions P1, P3-P7, scored from the same numbers (P2: oracle_check)."""
import gzip, json, os, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
MODES = ('default', 'witness', 'dead-ends', 'witness+dead-ends')
def load(mode, w, e, s):
    p = os.path.join(HERE, 'cells_' + mode, '%s_%s_%s' % (w, e, s), 'rep01', 'updates.jsonl.gz')
    return [json.loads(l) for l in gzip.open(p, 'rt')] if os.path.exists(p) else None
def med(us, f): return 1000 * statistics.median(f(u) for u in us)
cells = [(w, e, s) for w in ('wl_example', 'wl_ifi', 'wl_airtel1') for e in ('apkeep', 'ndd-apkeep')
         for s in ('s1', 's2', 's3')] + [('wl_cloud', 'ndd-apkeep', s) for s in ('s1', 's2', 's3')]
R = {}
print('| workload | engine | stream | mode | re-checked | vs default | verdicts = default | t_recheck median ms | t_total median ms |')
print('|---|---|---|---|---:|---:|---|---:|---:|')
for w, e, s in cells:
    base = load('default', w, e, s)
    for m in MODES:
        us = load(m, w, e, s)
        if us is None or base is None:
            print('| %s | %s | %s | %s | missing | | | | |' % (w, e, s, m)); continue
        n = len(us) == len(base)
        same = n and all(sorted(map(str, a['changed'])) == sorted(map(str, b['changed'])) for a, b in zip(us, base))
        tot, b0 = sum(u['rechecked'] for u in us), sum(u['rechecked'] for u in base)
        rc, tt = med(us, lambda u: u['t_recheck_s']), med(us, lambda u: u['t_update_s'] + u['t_recheck_s'])
        R[(w, e, s, m)] = dict(tot=tot, same=same, rc=rc, n=len(us))
        print('| %s | %s | %s | %s | %d | %s | %s | %.2f | %.2f |' % (
            w, e, s, m, tot, '' if m == 'default' else ('%+.0f%%' % (100.0 * (tot - b0) / b0) if b0 else 'n/a'),
            same, rc, tt))
def cut(w, e, s, m):
    b, x = R[(w, e, s, 'default')]['tot'], R[(w, e, s, m)]['tot']
    return (b - x) / b if b else 0.0
print()
print('P1 verdicts equal everywhere:', all(r['same'] for r in R.values()))
p3 = [(k[:3]) for k in R if k[3] == 'witness+dead-ends' and R[k]['tot'] > R[k[:3] + ('default',)]['tot']]
print('P3 witness+dead-ends <= default everywhere:', not p3, p3)
print('P4 wl_cloud witness cut S1 %.0f%%, S2 %.0f%% (>= 25%% each)' % (
    100 * cut('wl_cloud', 'ndd-apkeep', 's1', 'witness'), 100 * cut('wl_cloud', 'ndd-apkeep', 's2', 'witness')))
print('P5 wl_airtel1 S3 witness cut: apkeep %.0f%%, ndd-apkeep %.0f%% (>= 30%% each)' % (
    100 * cut('wl_airtel1', 'apkeep', 's3', 'witness'), 100 * cut('wl_airtel1', 'ndd-apkeep', 's3', 'witness')))
print('P6 wl_ifi S2 dead-ends cut: apkeep %.0f%%, ndd-apkeep %.0f%% (>= 20%% each)' % (
    100 * cut('wl_ifi', 'apkeep', 's2', 'dead-ends'), 100 * cut('wl_ifi', 'ndd-apkeep', 's2', 'dead-ends')))
worst = max(((R[k]['rc'] / R[k[:3] + ('default',)]['rc'] if R[k[:3] + ('default',)]['rc'] else 0, k)
             for k in R if k[3] != 'default'))
print('P7 largest t_recheck median ratio vs default: %.2f at %s (<= 1.5)' % worst)
