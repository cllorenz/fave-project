"""Re-check rule check: the calibration's NDD-APKeep cells (current rule, OR of both sides)
against variant F (forwarded side only) and, on wl_cloud, variant V (changed element
in the footprint, no packet-set test). Per stream: re-checks summed, their share of
all checks, verdict changes per update equal to the calibration's, F's set inside the
current rule's set on every update, and medians of t_recheck / t_total in ms."""
import gzip, json, os, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.environ.get('CAL_CELLS', os.path.join(HERE, '..', 'cells'))
def load(d):
    p = d + '/rep01/updates.jsonl.gz'
    if not os.path.exists(p): return None
    return [json.loads(l) for l in gzip.open(p, 'rt')]
def nchecks(d):
    return json.load(open(d + '/rep01/head.json')).get('checks')
def med(us, k): return round(1000 * statistics.median(u[k] for u in us), 2)
def ttot(u): return u['t_update_s'] + u['t_recheck_s']
print('| workload | stream | rule | re-checked | per update, share of checks | verdict changes = current | inside current, updates | t_recheck median ms | t_total median ms |')
print('|---|---|---|---:|---:|---|---:|---:|---:|')
for w in ('wl_example', 'wl_ifi', 'wl_airtel1', 'wl_cloud'):
    for s in ('s1', 's2', 's3'):
        name = '%s_ndd-apkeep_%s' % (w, s)
        cur = load(os.path.join(R, name))
        n = nchecks(os.path.join(R, name))
        rows = [('current', cur), ('F', load(os.path.join(HERE, 'cells', name)))]
        if w == 'wl_cloud': rows.append(('V', load(os.path.join(HERE, 'V_cells', name))))
        for label, us in rows:
            if us is None: continue
            assert len(us) == len(cur), (w, s, label)
            tot = sum(u['rechecked'] for u in us)
            same = all(sorted(map(str, a['changed'])) == sorted(map(str, b['changed'])) for a, b in zip(us, cur))
            inside = sum(set(map(tuple, a['affected'])) <= set(map(tuple, b['affected'])) for a, b in zip(us, cur))
            tt = round(1000 * statistics.median(ttot(u) for u in us), 2)
            print('| %s | %s | %s | %d | %.3f | %s | %d of %d | %s | %s |' % (
                w, s, label, tot, tot / len(us) / n, same, inside, len(us), med(us, 't_recheck_s'), tt))
