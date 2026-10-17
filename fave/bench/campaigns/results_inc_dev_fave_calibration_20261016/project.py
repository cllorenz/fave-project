"""Sizing for the D16 indicative run from this calibration's records: per D16
cell, its stream length through FaVe and an estimate of its wall time --
build + first check, plus the stream at the calibration's MEAN rates over its
first 50 updates. For the queue's order and for knowing which cells the 12 h
cap will stop; NOT a result, and the first 50 updates are not the stream
(S1 starts with deletes of the last routes, S3 with the first links).
Run from fave/: python3 <this>. Writes projections.json here; needs cells/."""
import gzip, json, math, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAP_S = 12 * 3600
#: stream lengths through FaVe (util/fave_streams.py, counted 2026-10-17):
#: workload -> (rule units, links)
UNITS = {'wl_airtel1': (39500, 84), 'wl_airtel2': (39500, 84), 'wl_cloud': (1741, 165),
         'wl_up': (3570, 590), 'wl_stanford': (8792, 1468), 'wl_i2': (77841, 297),
         'wl_tum': (4043, 495)}
S4_N = 1000                                     # C and E S4 cells: limit-updates


def length(w, s):
    rules, links = UNITS[w]
    return {'s1': 2 * rules, 's2': 2 * max(1, int(round(0.2 * rules))), 's3': 2 * links,
            's4': S4_N}[s]


def records(name):
    p = os.path.join(HERE, 'cells', name, 'rep01', 'updates.jsonl.gz')
    if not os.path.exists(p):
        return []
    with gzip.open(p, 'rt') as raw:
        return [json.loads(l) for l in raw]


def head(name):
    try:
        with open(os.path.join(HERE, 'cells', name, 'rep01', 'head.json')) as raw:
            return json.load(raw)
    except OSError:
        return {}


def rate(w, e, s, fp):
    """ (build_s, mean update-side s, mean re-check s, source cell) """
    kind = {'s4': 'C'}.get(s, 'D' if fp == 'coarse' else 'A')
    name = '%s_%s_%s_%s%s' % (kind, w, e, s, '_coarse' if kind == 'D' else '')
    ups = records(name)
    if not ups and kind != 'C':                 # the ONE_CELL engines: S2 only
        name = 'A_%s_%s_s2' % (w, e)
        ups = records(name)
    b = head(name).get('build_and_first_check_s')
    if not ups or b is None:
        return None
    upd = statistics.mean(r.get('t_model_s', 0) + r.get('t_diff_s', 0) + r['t_update_s'] for r in ups)
    chk = statistics.mean(r['t_recheck_s'] for r in ups)
    return b, upd, chk, name


def estimate(w, e, s, fp='default', batch=1, oracle=False):
    r = rate(w, e, s, fp)
    if r is None:
        return {'est_s': None, 'basis': 'no calibration record'}
    b, upd, chk, src = r
    n = length(w, s)
    batches = 1 if batch == 'all' else math.ceil(n / batch)
    t = b + n * upd + batches * chk
    if oracle:
        t *= 2                                  # it builds from zero at checkpoints (D11's rule)
    return {'est_s': round(t), 'updates': n, 'capped': t > CAP_S, 'basis': src}


def main():
    out = {}
    q = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else None
    for c in q or []:
        w = c['workload'].split('/')[1]
        fp = 'coarse' if c.get('footprint') == 'coarse' else 'default'
        out[c['name']] = estimate(w, c['engine'], c['stream'], fp, c.get('batch', 1) if c.get('batch', 1) < 10 ** 9 else 'all',
                                  'oracle-sample' in c)
    json.dump(out, open(os.path.join(HERE, 'projections.json'), 'w'), indent=1)
    est = [v['est_s'] for v in out.values() if v['est_s'] is not None]
    print('%d cells, %d without a record, %d over the cap; %.0f cell-hours (capped at 12 h)' % (
        len(out), sum(1 for v in out.values() if v['est_s'] is None),
        sum(1 for v in out.values() if v.get('capped')), sum(min(x, CAP_S) for x in est) / 3600))


if __name__ == '__main__':
    main()
