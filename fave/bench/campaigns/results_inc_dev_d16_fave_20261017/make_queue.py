"""The D16 indicative run through FaVe (INCREMENTAL_PLAN.md D13, D15, D16) as
an incremental_queue.py queue. Writes queue.json; est_h from the calibration's
project.py (results_inc_dev_fave_calibration_20261016/projections.json, made
from this queue), mem_mb by the rule below. Run from fave/:
python3 <this> [--bdd-cloud]   (--bdd-cloud: BDD-APKeep's wl_cloud cells
beyond A, which D11 left out for a 3.24 h build; 1,352 s in the calibration)."""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(HERE, '..', 'results_inc_dev_fave_calibration_20261016')
OUT = os.path.join(HERE, 'queue.json')
BDD_CLOUD = '--bdd-cloud' in sys.argv

_SPLIT = {'checks': '../checks.json', 'files': 'topology=device_topology.json,policies=probes.json'}
WL = {
    'wl_airtel1': ('bench/wl_airtel1', {}),
    'wl_airtel2': ('bench/wl_airtel2', {}),
    'wl_cloud': ('bench/wl_cloud', {}),
    'wl_up': ('bench/wl_up', {}),
    'wl_stanford': ('bench/wl_stanford/stanford-json', _SPLIT),
    'wl_i2': ('bench/wl_i2/i2-json', _SPLIT),
    'wl_tum': ('bench/wl_tum', {}),
}
GRID = tuple(WL)                                    # D13 as cut by D15
ENGINES = ('netplumber', 'veriflow', 'apkeep', 'ndd-apkeep')
NO_CELL = {('wl_stanford', 'apkeep'), ('wl_i2', 'apkeep')}     # D13
S4_WL = ('wl_cloud', 'wl_up', 'wl_tum')             # D15
FOOTPRINTED = ('veriflow', 'apkeep', 'ndd-apkeep')
INDICATIVE = ('wl_cloud', 'wl_airtel1')             # D15: witness / dead ends alone
CAP_S = 12 * 3600                                   # D16
S4_N = 1000

# Memory, which is also the cell's RSS limit. A JVM engine (BDD-APKeep,
# NDD-APKeep) runs with the JVM's default heap cap, a quarter of RAM (15.5 GB
# here), and grows its heap towards it before it collects: its RSS says when
# it collected, not what it needs (the calibration's BDD-APKeep wl_tum cells
# stopped at 12 GB in their build, one finished at 11.8 GB). So: the cap plus
# 2.5 GB, 18 GB. Otherwise 1.3x the largest peak of the workload x engine in
# the calibration, at least 4 GB, rounded up to whole GB; an oracle cell (it
# builds the network a second time) 1.6x. VeriFlow-FR on wl_tum: the
# calibration's peak was its 4 GB limit, so 1.3x item 59's whole-run 2,960 MB
# is not enough evidence -- 8 GB.
JVM_MB = 18432
PEAK = {}
with open(os.path.join(CAL, 'cells.tsv')) as raw:
    for r in csv.DictReader(raw, delimiter='\t'):
        k = (r['workload'], r['engine'])
        PEAK[k] = max(PEAK.get(k, 0), int(float(r['peak_rss_mb'] or 0)))


def mem(w, e, oracle=False):
    if e in ('apkeep', 'ndd-apkeep'):
        return JVM_MB
    if (w, e) == ('wl_tum', 'veriflow'):
        return 8192
    mb = (1.6 if oracle else 1.3) * PEAK.get((w, e), 0)
    return int(-(-max(mb, 4096) // 1024) * 1024)


PROJ = {}
pp = os.path.join(CAL, 'projections.json')
if os.path.exists(pp):
    with open(pp) as raw:
        PROJ = json.load(raw)

cells = []


def add(name, w, e, s, **kw):
    if (w, e) == ('wl_cloud', 'apkeep') and not name.startswith('A_') and not BDD_CLOUD:
        return
    d, extra = WL[w]
    cell = {'name': name, 'workload': d, 'engine': e, 'stream': s,
            'mem_mb': mem(w, e, 'oracle-sample' in kw), 'limit-wall': CAP_S}
    est = (PROJ.get(name) or {}).get('est_s')
    # no projection: assume the cap, so the unknown cell starts early
    cell['est_h'] = round(min(est, CAP_S) / 3600, 2) if est is not None else CAP_S / 3600
    cell.update(extra)
    cell.update(kw)
    cells.append(cell)


for w in GRID:
    for e in ENGINES:
        if (w, e) in NO_CELL:
            continue
        for s in ('s1', 's2', 's3'):                                    # A
            add('A_%s_%s_%s' % (w, e, s), w, e, s)
        for b in (10, 100, 0):                                          # B
            add('B_%s_%s_s2_b%s' % (w, e, b or 'all'), w, e, 's2', batch=(b or 10 ** 9))
        add('E_%s_%s_s2_oracle' % (w, e), w, e, 's2',                   # E
            **{'oracle-sample': 50, 'oracle-every': 1000})
        if e in FOOTPRINTED:                                            # D
            modes = ['coarse'] + (['witness', 'dead-ends'] if w in INDICATIVE else [])
            for m in modes:
                for s in ('s1', 's2', 's3'):
                    add('D_%s_%s_%s_%s' % (w, e, s, m), w, e, s, footprint=m)
for w in S4_WL:                                                         # C, E on S4
    for e in ENGINES:
        add('C_%s_%s_s4' % (w, e), w, e, 's4', **{'limit-updates': S4_N})
        add('E_%s_%s_s4_oracle' % (w, e), w, e, 's4',
            **{'limit-updates': S4_N, 'oracle-sample': 50, 'oracle-every': 250})
cells.sort(key=lambda c: -c['est_h'])               # longest first
with open(OUT, 'w') as out:
    json.dump(cells, out, indent=1)
by = {}
for c in cells:
    by[c['name'][0]] = by.get(c['name'][0], 0) + 1
print('%d cells %s, %.0f estimated cell-hours (capped)' % (len(cells), dict(sorted(by.items())), sum(c['est_h'] for c in cells)))
