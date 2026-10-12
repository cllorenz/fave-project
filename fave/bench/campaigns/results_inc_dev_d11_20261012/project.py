"""Projection of full-stream cell wall times from every dev incremental cell
recorded before the D11 run. Writes projections.json and rates.json next to
itself (make_queue.py reads them). Run from anywhere."""
import glob, gzip, json, os, re, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(HERE)
rows = {}
SUB_RANK = {'cells_fixed2': 4, 'cells_jar_rerun': 3, 'cells': 2, 'cells_fixed': 0, 'interrupted': -1}
for head in glob.glob(root + '/results_inc_dev_*/**/rep01/head.json', recursive=True):
    d = os.path.dirname(head)
    try:
        h = json.load(open(head))
    except Exception:
        continue
    if head.startswith(HERE):       # this run's own cells project nothing
        continue
    if h.get('oracle'):
        continue
    try:   # a crash or an interruption projects nothing (a did-not-finish still has its per-update times)
        if json.load(open(os.path.join(d, 'cell.json')))['outcome'] in ('error', 'interrupted', 'oracle_failed'):
            continue
    except Exception:
        continue
    up = os.path.join(d, 'updates.jsonl.gz')
    if os.path.exists(up):
        recs = [json.loads(l) for l in gzip.open(up, 'rt')]
    elif os.path.exists(up[:-3]):
        recs = [json.loads(l) for l in open(up[:-3])]
    else:
        continue
    if not recs:
        continue
    per = [r['t_update_s'] + r['t_recheck_s'] for r in recs]
    w = os.path.basename(h['workload'].rstrip('/'))
    w = {'stanford-json': 'wl_stanford', 'i2-json': 'wl_i2'}.get(w, w)
    mode = ','.join(h.get('footprint') or []) or 'coarse'
    key = (w, h['engine'], h['stream'], mode)
    parts = d.split('/campaigns/')[1].split('/')
    # within one run directory: the m2 code (cells_fixed2) is what D11 runs; then the declared re-run
    run = (parts[0], SUB_RANK.get(parts[1], 1) if len(parts) > 3 else 1)
    n_full = {'s1': 2 * h['rules'], 's2': 2 * max(1, round(0.2 * h['rules'])), 's3': 2 * h['links']}[h['stream']]
    mean = statistics.mean(per)
    rows.setdefault(key, []).append((run, len(per), mean, statistics.median(per), h.get('build_and_first_check_s', 0), n_full))
print('%-11s %-10s %-3s %-18s %6s %9s %9s %8s %8s %10s' % ('workload', 'engine', 's', 'mode', 'n', 'mean ms', 'med ms', 'build s', 'N full', 'proj h'))
for key in sorted(rows):
    run, n, mean, med, build, N = sorted(rows[key])[-1]     # latest run
    proj = (build + N * mean) / 3600
    print('%-11s %-10s %-3s %-18s %6d %9.2f %9.2f %8.1f %8d %10.2f' % (key + (n, 1000 * mean, 1000 * med, build, N, proj)))

# projections.json for d11/make_queue.py: key "workload|engine|stream|mode",
# value the projected wall hours (latest run), with 20% and 3 min of margin;
# the engine's default mode is also written as "default"
DEFAULT = {'apkeep': 'witness,dead-ends', 'ndd-apkeep': 'witness,dead-ends', 'veriflow': 'coarse',
           'netplumber': 'coarse'}
out = {}
for key in sorted(rows):
    run, n, mean, med, build, N = sorted(rows[key])[-1]
    h = 1.2 * (build + N * mean) / 3600 + 0.05
    w, e, s, m = key
    out['|'.join(key)] = round(h, 3)
    if DEFAULT.get(e) == m:
        out['|'.join((w, e, s, 'default'))] = round(h, 3)
json.dump(out, open(os.path.join(HERE, 'projections.json'), 'w'), indent=1, sort_keys=True)

# rates.json: per key the latest run's mean seconds per update, its build +
# first check, and the full stream's length -- make_queue.py spaces the
# oracle's full checkpoints by them
rates = {}
for key in sorted(rows):
    run, n, mean, med, build, N = sorted(rows[key])[-1]
    rates['|'.join(key)] = {'mean_s': round(mean, 4), 'build_s': round(build, 1), 'n_full': N}
    if DEFAULT.get(key[1]) == key[3]:
        rates['|'.join(key[:3] + ('default',))] = rates['|'.join(key)]
json.dump(rates, open(os.path.join(HERE, 'rates.json'), 'w'), indent=1, sort_keys=True)

# peaks.json: the largest peak RSS (MB) any dev cell of a workload x engine
# reached, apart for oracle cells -- make_queue.py sizes each cell's memory by it
peaks = {}
for cj in glob.glob(root + '/results_inc_dev_*/**/rep01/cell.json', recursive=True):
    if cj.startswith(HERE):
        continue
    d = os.path.dirname(cj)
    try:
        c, h = json.load(open(cj)), json.load(open(os.path.join(d, 'head.json')))
    except Exception:
        continue
    w = os.path.basename(h['workload'].rstrip('/'))
    w = {'stanford-json': 'wl_stanford', 'i2-json': 'wl_i2'}.get(w, w)
    k = '|'.join((w, h['engine'], 'oracle' if h.get('oracle') else 'plain'))
    peaks[k] = max(peaks.get(k, 0), c['measured']['peak_rss_mb'])
json.dump(peaks, open(os.path.join(HERE, 'peaks.json'), 'w'), indent=1, sort_keys=True)
