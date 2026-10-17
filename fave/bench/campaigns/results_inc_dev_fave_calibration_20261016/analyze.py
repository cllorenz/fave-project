"""The calibration's cells, tabulated and scored against PROTOCOL.txt's C1-C7.
Run from fave/: python3 <this>. Writes cells.tsv and scores.json here.
Reads only the raw records (cells/*/rep01) and, for C3/C4, D11's
(results_inc_dev_d11_20261012)."""
import gzip, json, os, statistics, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
D11 = os.path.join(HERE, '..', 'results_inc_dev_d11_20261012')
N = 50


def _json(path):
    try:
        with open(path) as raw:
            return json.load(raw)
    except (OSError, ValueError):
        return None


def _lines(path):
    for p in (path, path + '.gz'):
        if os.path.exists(p):
            with (gzip.open(p, 'rt') if p.endswith('.gz') else open(p)) as raw:
                return [json.loads(l) for l in raw if l.strip()]
    return []


def total(r):
    return r.get('t_model_s', 0) + r.get('t_diff_s', 0) + r['t_update_s'] + r['t_recheck_s']


def resend(r):
    return any(m.get('kind') == 'resend' for m in r.get('messages', [])) or \
        ('t_model_s' in r and 'messages' not in r)


def cell(cells, name):
    d = os.path.join(cells, name, 'rep01')
    status = [json.loads(l) for l in open(os.path.join(d, 'cell.status.jsonl'))] \
        if os.path.exists(os.path.join(d, 'cell.status.jsonl')) else []
    head, end = _json(os.path.join(d, 'head.json')) or {}, _json(os.path.join(d, 'end.json'))
    ups = _lines(os.path.join(d, 'updates.jsonl'))
    last = status[-1] if status else {}
    return {'head': head, 'end': end, 'ups': ups,
            'peak_rss_mb': max([s.get('peak_rss_mb', 0) for s in status] or [0]),
            'tripped': last.get('limit_tripped'), 'wall_s': last.get('elapsed_s')}


def main():
    queue = _json(os.path.join(HERE, 'queue.json'))
    queue = queue if isinstance(queue, list) else queue['cells']
    log = open(os.path.join(HERE, 'run.log')).read().splitlines()
    outcome = {l.split()[2]: l.split('outcome=')[1].split()[0] for l in log if ' end ' in l}
    rows = []
    for q in queue:
        c = cell(os.path.join(HERE, 'cells'), q['name'])
        ups = c['ups']
        refused = sum(len(r.get('refused') or []) for r in ups)
        ops = sum(r.get('n', 1) for r in ups)
        rows.append({
            'name': q['name'], 'kind': q['name'][0], 'workload': os.path.basename(q['workload'].split('/')[1]) if q['workload'].count('/') > 1 else os.path.basename(q['workload']),
            'engine': q['engine'], 'stream': q['stream'], 'mem_mb': q['mem_mb'],
            'outcome': outcome.get(q['name'], 'not_run'), 'tripped': c['tripped'],
            'wall_s': c['wall_s'], 'peak_rss_mb': c['peak_rss_mb'],
            'build_s': c['head'].get('build_and_first_check_s'),
            'checks': c['head'].get('checks'),
            'rss_after_build_mb': c['head'].get('rss_after_build_mb'),
            'records': len(ups), 'ops': ops, 'refused_ops': refused,
            'median_ms': round(1000 * statistics.median(map(total, ups)), 3) if ups else None,
            'median_recheck_ms': round(1000 * statistics.median(r['t_recheck_s'] for r in ups), 3) if ups else None,
            'median_rechecked': statistics.median(r['rechecked'] for r in ups) if ups else None,
            'resends': sum(1 for r in ups if resend(r)),
            'rss_growth_mb_per_record': round((ups[-1]['rss_mb'] - ups[0]['rss_mb']) / max(1, len(ups) - 1), 2) if ups else None,
        })
    cols = list(rows[0])
    with open(os.path.join(HERE, 'cells.tsv'), 'w') as out:
        out.write('\t'.join(cols) + '\n')
        for r in rows:
            out.write('\t'.join('' if r[k] is None else str(r[k]) for k in cols) + '\n')

    # D11: the same cell's first N records, at the adapter
    d11rows = {}
    for line in open(os.path.join(D11, 'cells.tsv')).read().splitlines()[1:]:
        f = line.split('\t')
        d11rows.setdefault(f[0], f)

    def d11_first(name):
        ups = _lines(os.path.join(D11, 'cells', name, 'rep01', 'updates.jsonl'))[:N]
        return statistics.median(map(total, ups)) if ups else None

    scores = {}
    errors = [r['name'] for r in rows if r['outcome'] not in ('measured', 'did_not_finish')]
    scores['C1'] = {'held': not errors, 'not_measured_or_dnf': errors}
    mem = [r['name'] for r in rows if r['tripped'] == 'rss']
    scores['C2'] = {'held': not mem, 'memory_stops': mem}
    c3 = []
    for r in rows:
        if r['kind'] == 'A' and r['engine'] == 'netplumber' and r['workload'] in \
                ('wl_airtel1', 'wl_airtel2', 'wl_cloud', 'wl_stanford', 'wl_i2') and r['median_ms'] is not None:
            base = d11_first(r['name'])
            if base is None:
                c3.append({'cell': r['name'], 'd11': None})
                continue
            bound = max(10 * base, base + 0.005)
            c3.append({'cell': r['name'], 'fave_ms': r['median_ms'], 'd11_first50_ms': round(1000 * base, 3),
                       'bound_ms': round(1000 * bound, 3), 'held': r['median_ms'] / 1000 <= bound})
    scores['C3'] = {'held': all(x.get('held') for x in c3), 'cells': c3}
    def d11_checks(name):
        return (_json(os.path.join(D11, 'cells', name, 'rep01', 'head.json')) or {}).get('checks')

    c4 = []
    for w in sorted({r['workload'] for r in rows}):
        mine = [r for r in rows if r['workload'] == w and r['engine'] == 'ndd-apkeep' and r['build_s']]
        now = [r['build_s'] for r in mine]
        then = [float(f[14]) for f in d11rows.values() if f[2] == w and f[3] == 'ndd-apkeep' and f[14]]
        theirs = {d11_checks(f[0]) for f in d11rows.values() if f[2] == w and f[3] == 'ndd-apkeep'}
        if now and then and theirs != {r['checks'] for r in mine}:
            # not the same first check (wl_tum: D11 had none, D16 its 8,497)
            c4.append({'workload': w, 'comparable': False, 'checks': sorted({r['checks'] for r in mine}),
                       'd11_checks': sorted(x for x in theirs if x is not None)})
        elif now and then:
            c4.append({'workload': w, 'median_build_s': round(statistics.median(now), 1),
                       'd11_median_build_s': round(statistics.median(then), 1),
                       'held': statistics.median(now) < statistics.median(then)})
    scores['C4'] = {'held': all(x['held'] for x in c4 if x.get('comparable', True)), 'workloads': c4}
    c5 = {}
    for r in rows:
        if r['name'] == 'A_wl_up_netplumber_s2':
            ups = [u for u in cell(os.path.join(HERE, 'cells'), r['name'])['ups'] if resend(u)]
            mdl = statistics.median(u['t_model_s'] + u['t_diff_s'] for u in ups)
            upd = statistics.median(u['t_update_s'] for u in ups)
            c5 = {'resends': len(ups), 'median_model_plus_diff_ms': round(1000 * mdl, 3),
                  'median_update_ms': round(1000 * upd, 3), 'held': mdl > upd}
    scores['C5'] = c5
    c6 = [{'cell': r['name'], 'refused_ops': r['refused_ops'], 'ops': r['ops'],
           'held': r['ops'] > 0 and r['refused_ops'] <= 0.03 * r['ops']}
          for r in rows if r['workload'] == 'wl_up' and r['engine'] in ('apkeep', 'ndd-apkeep')]
    scores['C6'] = {'held': all(x['held'] for x in c6), 'cells': c6}
    stamp = lambda l: datetime.strptime(l.split()[0], '%Y-%m-%dT%H:%M:%SZ')
    starts = [stamp(l) for l in log if ' start ' in l]
    ends = [stamp(l) for l in log if 'runner exit' in l]
    hours = (ends[-1] - starts[0]).total_seconds() / 3600 if ends else None
    scores['C7'] = {'hours': round(hours, 2) if hours else None, 'held': hours is not None and hours <= 24}
    with open(os.path.join(HERE, 'scores.json'), 'w') as out:
        json.dump(scores, out, indent=1)
    for k, v in scores.items():
        print(k, 'HELD' if v.get('held') else 'FAILED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
