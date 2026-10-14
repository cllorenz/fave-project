"""D11 analysis: a per-cell table (cells.tsv) and the scoring of PROTOCOL.txt's
P1-P7 (scores.json), from the raw records in cells/ and run.log. Written
after the run (2026-10-14); reads, never rewrites, the records. Run from
anywhere."""
import glob, gzip, json, os, re, statistics
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CELLS = os.path.join(HERE, 'cells')
queue = json.load(open(os.path.join(HERE, 'queue.json')))
queue = queue if isinstance(queue, list) else queue['cells']
DEFAULT = {'apkeep': 'witness,dead-ends', 'ndd-apkeep': 'witness,dead-ends',
           'veriflow': 'coarse', 'netplumber': 'coarse'}


def wl_name(path):
    w = os.path.basename(path.rstrip('/'))
    return {'stanford-json': 'wl_stanford', 'i2-json': 'wl_i2'}.get(w, w)


def records(d, name):
    p = os.path.join(d, name)
    if os.path.exists(p + '.gz'):
        return [json.loads(l) for l in gzip.open(p + '.gz', 'rt')]
    if os.path.exists(p):
        return [json.loads(l) for l in open(p)]
    return []


def per_record(r):
    """ a record's whole cost: S4's model and diff times, then update and re-check """
    return r.get('t_model_s', 0) + r.get('t_diff_s', 0) + r['t_update_s'] + r['t_recheck_s']


rows = []
for c in queue:
    d = os.path.join(CELLS, c['name'], 'rep01')
    row = dict(name=c['name'], group=c['name'][0], workload=wl_name(c['workload']),
               engine=c['engine'], stream=c['stream'], batch=c.get('batch', 1),
               oracle=bool(c.get('oracle-every')), mem_mb=c['mem_mb'], cap_s=c['limit-wall'])
    try:
        cell = json.load(open(os.path.join(d, 'cell.json')))
    except FileNotFoundError:
        row['outcome'] = 'missing'
        rows.append(row)
        continue
    head = {}
    if os.path.exists(os.path.join(d, 'head.json')):
        head = json.load(open(os.path.join(d, 'head.json')))
    fp = head.get('footprint')
    row['footprint'] = ','.join(fp) if fp else (c.get('footprint') or 'coarse')
    ups = records(d, 'updates.jsonl')
    per = [per_record(r) for r in ups]
    ops = sum(r.get('n', 1) for r in ups)
    refused = sum(len(r['refused']) if isinstance(r.get('refused'), list) else bool(r.get('refused')) for r in ups)
    full = [o for o in records(d, 'oracle.jsonl') if o.get('full')]
    row.update(outcome=cell['outcome'], tripped=cell.get('limit_tripped'),
               wall_s=round(cell['measured']['wall_s'], 1),
               peak_rss_mb=cell['measured']['peak_rss_mb'],
               build_s=head.get('build_and_first_check_s'),
               ops=ops, stream_len=head.get('updates') or head.get('limit_updates'),
               records=len(ups), refused_ops=refused,
               median_ms=round(1000 * statistics.median(per), 3) if per else None,
               mean_ms=round(1000 * statistics.mean(per), 3) if per else None,
               sum_recheck_s=round(sum(r['t_recheck_s'] for r in ups), 3),
               sum_rechecked=sum(r.get('rechecked', 0) for r in ups),
               full_checkpoints=len(full),
               full_mismatch=sum(1 for o in full if o.get('full_vs_zero') or o.get('selective_vs_full')))
    rows.append(row)

cols = ['name', 'group', 'workload', 'engine', 'stream', 'footprint', 'batch', 'oracle', 'outcome',
        'tripped', 'wall_s', 'cap_s', 'peak_rss_mb', 'mem_mb', 'build_s', 'ops', 'stream_len',
        'records', 'refused_ops', 'median_ms', 'mean_ms', 'sum_recheck_s', 'sum_rechecked',
        'full_checkpoints', 'full_mismatch']
with open(os.path.join(HERE, 'cells.tsv'), 'w') as out:
    out.write('\t'.join(cols) + '\n')
    for r in rows:
        out.write('\t'.join('' if r.get(k) is None else str(r.get(k)) for k in cols) + '\n')

by = {r['name']: r for r in rows}
scores = {}

# P1 -- no error, no oracle_failed
bad = [r['name'] for r in rows if r['outcome'] in ('error', 'oracle_failed')]
from collections import Counter
scores['P1'] = dict(held=not bad, error_or_oracle_failed=bad,
                    outcomes=dict(sorted(Counter(r['outcome'] for r in rows).items())))

# P2 -- 90..150 stopped by the wall cap; none by memory
wall = [r['name'] for r in rows if r.get('tripped') == 'wall']
rss = [r['name'] for r in rows if r.get('tripped') == 'rss']
scores['P2'] = dict(held=90 <= len(wall) <= 150 and not rss, wall=len(wall), rss=len(rss),
                    rss_cells=[(n, by[n]['peak_rss_mb'], by[n]['mem_mb'], by[n]['ops']) for n in rss])

# P3 -- every E cell has a full checkpoint
e = [r for r in rows if r['group'] == 'E']
none = [r['name'] for r in e if not r.get('full_checkpoints')]
scores['P3'] = dict(held=not none, e_cells=len(e), without_full=none,
                    without_full_not_error=[n for n in none if by[n]['outcome'] != 'error'],
                    mismatches=[r['name'] for r in e if r.get('full_mismatch')])

# P4 -- within 72 h
log = open(os.path.join(HERE, 'run.log')).read()
stamps = re.findall(r'^(\S+Z) (?:start|end|runner exit)', log, re.M)
t0 = datetime.fromisoformat(stamps[0].replace('Z', '+00:00'))
t1 = datetime.fromisoformat(re.search(r'^(\S+Z) runner exit', log, re.M).group(1).replace('Z', '+00:00'))
hours = (t1 - t0).total_seconds() / 3600
scores['P4'] = dict(held=hours <= 72, hours=round(hours, 2))

# P5 -- ablation: witness+dead-ends re-checks <= coarse and <= each mode alone
abl = {}
for r in rows:
    if r['group'] in ('A', 'D') and r['stream'] in ('s1', 's2', 's3') and r['engine'] != 'netplumber' \
            and r['batch'] == 1 and not r['oracle']:
        abl.setdefault((r['workload'], r['engine'], r['stream']), {})[r.get('footprint')] = r
p5 = []
for key, modes in sorted(abl.items()):
    want = ('coarse', 'witness', 'dead-ends', 'witness,dead-ends')
    if not all(m in modes and modes[m]['outcome'] == 'measured' for m in want):
        continue
    s = {m: modes[m]['sum_rechecked'] for m in want}
    p5.append(dict(key='|'.join(key), rechecked=s,
                   holds=s['witness,dead-ends'] <= min(s['coarse'], s['witness'], s['dead-ends'])))
scores['P5'] = dict(held=all(x['holds'] for x in p5), comparable=len(p5),
                    groups=len(abl), violations=[x for x in p5 if not x['holds']], all=p5)

# P6 -- batch "all" summed t_recheck <= batch 1
p6 = []
for r in rows:
    if r['group'] == 'B' and r['name'].endswith('_ball'):
        a = by.get('A_%s_%s_s2' % (r['workload'], r['engine']))
        if a and a['outcome'] == 'measured' and r['outcome'] == 'measured':
            p6.append(dict(key=r['workload'] + '|' + r['engine'], b1=a['sum_recheck_s'],
                           ball=r['sum_recheck_s'], holds=r['sum_recheck_s'] <= a['sum_recheck_s']))
scores['P6'] = dict(held=all(x['holds'] for x in p6), comparable=len(p6),
                    violations=[x for x in p6 if not x['holds']], all=p6)

# P7 -- A medians within 0.5-2x of the latest earlier dev record (four workloads)
SUB_RANK = {'cells_fixed2': 4, 'cells_jar_rerun': 3, 'cells': 2, 'cells_fixed': 0, 'interrupted': -1}
earlier = {}
for head in glob.glob(os.path.dirname(HERE) + '/results_inc_dev_*/**/rep01/head.json', recursive=True):
    if head.startswith(HERE):
        continue
    d = os.path.dirname(head)
    try:
        h = json.load(open(head))
        if h.get('oracle') or (h.get('batch') or 1) != 1:
            continue
        if json.load(open(os.path.join(d, 'cell.json')))['outcome'] in ('error', 'interrupted', 'oracle_failed'):
            continue
    except Exception:
        continue
    ups = records(d, 'updates.jsonl')
    if not ups:
        continue
    key = (wl_name(h['workload']), h['engine'], h['stream'], ','.join(h.get('footprint') or []) or 'coarse')
    parts = d.split('/campaigns/')[1].split('/')
    run = (parts[0], SUB_RANK.get(parts[1], 1) if len(parts) > 3 else 1)
    earlier.setdefault(key, []).append((run, statistics.median(per_record(x) for x in ups), d))
p7 = []
for r in rows:
    if r['group'] != 'A' or r['workload'] not in ('wl_example', 'wl_ifi', 'wl_airtel1', 'wl_cloud') \
            or r.get('median_ms') is None or r['refused_ops']:
        continue
    prev = earlier.get((r['workload'], r['engine'], r['stream'], r['footprint']))
    if not prev:
        continue
    run, med, d = sorted(prev)[-1]
    ratio = r['median_ms'] / (1000 * med) if med else None
    p7.append(dict(name=r['name'], earlier=d.split('/campaigns/')[1], earlier_ms=round(1000 * med, 3),
                   d11_ms=r['median_ms'], ratio=round(ratio, 2) if ratio else None,
                   within=ratio is not None and 0.5 <= ratio <= 2))
share = sum(x['within'] for x in p7) / len(p7) if p7 else None
scores['P7'] = dict(held=share is not None and share >= 0.9, pairs=len(p7),
                    within=sum(x['within'] for x in p7), share=round(share, 3) if share else None,
                    outside=[x for x in p7 if not x['within']], all=p7)

# not a prediction: cells whose engine refused operations -- every one of
# them ('hollow': the cell measured nothing), or some
scores['hollow'] = [(r['name'], r['outcome'], r['ops']) for r in rows
                    if r.get('ops') and r['refused_ops'] == r['ops']]
scores['some_refused'] = [(r['name'], r['outcome'], r['refused_ops'], r['ops']) for r in rows
                          if r.get('refused_ops') and r['refused_ops'] < r['ops']]

json.dump(scores, open(os.path.join(HERE, 'scores.json'), 'w'), indent=1, sort_keys=True)
for p in ('P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7'):
    s = scores[p]
    print(p, 'HELD' if s['held'] else 'FALSIFIED',
          {k: v for k, v in s.items() if k not in ('held', 'all') and not isinstance(v, list) or k in ('rss_cells', 'error_or_oracle_failed', 'without_full', 'violations', 'outside', 'mismatches')})
print('hollow', scores['hollow'])
print('some_refused', scores['some_refused'])

# tables.md: the A cells, median ms per update and the share of the stream done
WL = ['wl_example', 'wl_ifi', 'wl_airtel1', 'wl_airtel2', 'wl_cloud', 'wl_up', 'wl_stanford', 'wl_i2', 'wl_tum']
EN = ['netplumber', 'veriflow', 'apkeep', 'ndd-apkeep']
with open(os.path.join(HERE, 'tables.md'), 'w') as out:
    out.write('# D11 A cells: median ms per update (share of the stream done)\n\n'
              'Made by analyze.py from cells/. `-`: no cell. `hollow`: every operation refused. '
              'Outcome marks: `cap` stopped by the wall cap, `mem` by the memory limit, `ERR` error.\n')
    for s in ('s1', 's2', 's3'):
        out.write('\n## %s\n\n| workload | %s |\n|---|%s\n' % (s, ' | '.join(EN), '---:|' * len(EN)))
        for w in WL:
            cells = []
            for e in EN:
                r = by.get('A_%s_%s_%s' % (w, e, s))
                if not r or r.get('outcome') == 'missing':
                    cells.append('-')
                    continue
                if r.get('ops') and r['refused_ops'] == r['ops']:
                    cells.append('hollow')
                    continue
                mark = {'wall': ' cap', 'rss': ' mem'}.get(r.get('tripped'), '')
                if r['outcome'] == 'error':
                    mark = ' ERR'
                share = r['ops'] / r['stream_len'] if r.get('stream_len') else None
                med = '%.3g' % r['median_ms'] if r.get('median_ms') is not None else 'n/a'
                cells.append('%s (%s)%s' % (med, '%.0f%%' % (100 * share) if share is not None else '?', mark))
            out.write('| %s | %s |\n' % (w, ' | '.join(cells)))
