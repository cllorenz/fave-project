"""Committed summaries of the calibration's raw records (copied from D11's summarize.py: summaries in
git, the full records archived -- see summary/ARCHIVE.txt). Reads cells/,
never rewrites it, and writes summary/:

  heads.jsonl.gz       every cell's head.json without its initial verdicts,
                       plus their sha256 and the file of its stream
  initial_verdicts/    the initial verdicts, once per distinct set (every
                       engine agrees; wl_airtel1 and wl_airtel2 share one),
                       named by their sha256; INDEX.json names the workloads
  streams/             each distinct update stream once, named by the sha256
                       of its uncompressed records
  per_cell.jsonl.gz    per cell: distributions of every timing, by operation
                       type, along the stream; memory along the stream and
                       during the run; verdict flips; refusals by reason

What is NOT here: each update's `affected` pairs (92% of the records),
and the per-update timings themselves (only their distributions).
"""
import collections, glob, gzip, hashlib, json, os, re, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
CELLS = os.path.join(HERE, 'cells')
OUT = os.path.join(HERE, 'summary')
TIMES = ('t_model_s', 't_diff_s', 't_update_s', 't_recheck_s')
QS = (0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 0.999)


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))


def gz_write(path, text):
    # mtime 0: the same content gives the same bytes on every run
    with open(path, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as out:
        out.write(text.encode())


def dist(xs):
    """ n, sum, mean, min, quantiles and max; seconds rounded to 1 ns """
    if not xs:
        return None
    s = sorted(xs)
    q = {'p%s' % ('%g' % (100 * p)).replace('.', '_'): round(s[min(len(s) - 1, int(p * len(s)))], 9)
         for p in QS}
    return dict(n=len(s), sum=round(sum(s), 9), mean=round(statistics.mean(s), 9),
                min=round(s[0], 9), max=round(s[-1], 9), **q)


def total(r):
    return sum(r.get(k, 0) for k in TIMES)


def thin(points, k=100):
    """ at most k points, evenly spaced, the last always kept """
    if len(points) <= k:
        return points
    step = len(points) / k
    picked = [points[int(i * step)] for i in range(k)]
    return picked[:-1] + [points[-1]]


MASK = re.compile(r'\d+')


def summarize(cell, d, heads, streams, verdicts):
    head = json.load(open(os.path.join(d, 'head.json')))
    iv = head.pop('initial_verdicts', None)
    if iv is not None:
        key = hashlib.sha256(canon(iv).encode()).hexdigest()
        verdicts.setdefault(key, (set(), iv))[0].add(head['workload'])
        head['initial_verdicts_file'] = 'initial_verdicts/%s.json.gz' % key[:16]
        head['initial_verdicts_sha256'] = key
    sp = os.path.join(d, 'stream.jsonl.gz')
    if os.path.exists(sp):
        text = gzip.open(sp, 'rt').read()
        key = hashlib.sha256(text.encode()).hexdigest()
        streams.setdefault(key, text)
        head['stream_file'] = 'streams/%s.jsonl.gz' % key[:16]
    heads.append(dict(name=cell, **head))

    ups = [json.loads(l) for l in gzip.open(os.path.join(d, 'updates.jsonl.gz'), 'rt')] \
        if os.path.exists(os.path.join(d, 'updates.jsonl.gz')) else []
    row = dict(name=cell, records=len(ups), ops=sum(r.get('n', 1) for r in ups))
    row['timings'] = {k: dist([r[k] for r in ups if k in r]) for k in TIMES + ('t_total',)
                      if k == 't_total' or any(k in r for r in ups)}
    row['timings']['t_total'] = dist([total(r) for r in ups])
    row['t_each'] = dist([x for r in ups for x in (r.get('t_each_s') or [])])
    # by operation type: single-operation records only (a batch mixes them)
    by = collections.defaultdict(list)
    for r in ups:
        if r.get('n', 1) == 1 and r.get('ops'):
            by[r['ops'][0]].append(r)
    row['by_op'] = {op: {k: dist([r[k] for r in rs if k in r]) for k in ('t_update_s', 't_recheck_s')}
                    | {'t_total': dist([total(r) for r in rs]),
                       'rechecked': dist([r.get('rechecked', 0) for r in rs])}
                    for op, rs in sorted(by.items())}
    # along the stream: 20 equal segments of records
    seg = []
    if ups:
        m0 = ups[0].get('mono')
        k = max(1, -(-len(ups) // 20))
        for i in range(0, len(ups), k):
            part = ups[i:i + k]
            tt = [total(r) for r in part]
            seg.append(dict(first=i, records=len(part), ops=sum(r.get('n', 1) for r in part),
                            mean_s=round(statistics.mean(tt), 9), median_s=round(statistics.median(tt), 9),
                            rechecked=sum(r.get('rechecked', 0) for r in part),
                            rss_mb_end=part[-1].get('rss_mb'),
                            elapsed_end_s=round(part[-1]['mono'] - m0, 3) if m0 is not None else None))
    row['along'] = seg
    row['rss_mb'] = thin([[r.get('pos', i), r.get('rss_mb')] for i, r in enumerate(ups)])
    st = [json.loads(l) for l in open(os.path.join(d, 'cell.status.jsonl'))] \
        if os.path.exists(os.path.join(d, 'cell.status.jsonl')) else []
    row['status'] = thin([[s.get('elapsed_s'), s.get('peak_rss_mb'), s.get('available_mb')] for s in st])
    # the footprint's output: how many pairs it flagged, how many were re-asked
    row['affected'] = dist([len(r.get('affected') or []) for r in ups])
    row['rechecked'] = dist([r.get('rechecked', 0) for r in ups])
    flips = [c for r in ups for c in (r.get('changed') or [])]
    row['verdict_flips'] = dict(total=len(flips), distinct_checks=len({c[0] for c in flips}),
                                to_true=sum(1 for c in flips if c[2] is True),
                                to_false=sum(1 for c in flips if c[2] is False))
    refused = [(r.get('pos'), x) for r in ups for x in (r.get('refused') or [])]
    reasons = collections.Counter(MASK.sub('#', x[1] if isinstance(x, list) else str(x)) for _, x in refused)
    row['refused'] = dict(total=len(refused), by_reason=dict(reasons.most_common()),
                          first=[[p, x] for p, x in refused[:20]])
    return row


def main():
    os.makedirs(os.path.join(OUT, 'initial_verdicts'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'streams'), exist_ok=True)
    heads, streams, verdicts, rows = [], {}, {}, []
    for d in sorted(glob.glob(os.path.join(CELLS, '*', 'rep01'))):
        if not os.path.exists(os.path.join(d, 'head.json')):
            # stopped before its build ended (a memory limit): cells.tsv has it
            rows.append({'cell': d.split(os.sep)[-2], 'no_head': True})
            continue
        rows.append(summarize(d.split(os.sep)[-2], d, heads, streams, verdicts))
    for key, (_w, iv) in verdicts.items():
        gz_write(os.path.join(OUT, 'initial_verdicts', key[:16] + '.json.gz'), canon(iv))
    with open(os.path.join(OUT, 'initial_verdicts', 'INDEX.json'), 'w') as out:
        json.dump({key[:16]: sorted(w) for key, (w, _iv) in sorted(verdicts.items())}, out, indent=1)
    for key, text in streams.items():
        gz_write(os.path.join(OUT, 'streams', key[:16] + '.jsonl.gz'), text)
    gz_write(os.path.join(OUT, 'heads.jsonl.gz'), ''.join(canon(h) + '\n' for h in heads))
    gz_write(os.path.join(OUT, 'per_cell.jsonl.gz'), ''.join(canon(r) + '\n' for r in rows))
    print('cells %d, verdict sets %d, streams %d' % (len(rows), len(verdicts), len(streams)))


if __name__ == '__main__':
    main()
