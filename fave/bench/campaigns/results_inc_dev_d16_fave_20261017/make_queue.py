"""The D16 indicative run through FaVe, CONVERGED (INCREMENTAL_PLAN.md D13,
D15, D16, D17): the stream cells, from-zero-only cells (ad6, the wl_berkeley
series), recorded stops, a contention sample and bridge cells. Writes
queue.json (incremental_queue.py: everything but the two below),
contention_queue.json (serial, unpinned) and bridge_queue.json
(cell_queue.py: V5's layout). Writes queue.json; est_h from the calibration's
project.py (results_inc_dev_fave_calibration_20261016/projections.json, made
from this queue), mem_mb by the rule below. Run from fave/:
python3 <this> [--no-bdd-cloud]   (BDD-APKeep's wl_cloud cells beyond A, which
D11 left out for a 3.24 h build, are in since their trial)."""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..'))
CAL = os.path.join(HERE, '..', 'results_inc_dev_fave_calibration_20261016')
OUT = os.path.join(HERE, 'queue.json')
# included since the trial (results_inc_dev_bdd_cloud_trial_20261017, owner's
# rule "try BDD cloud before inclusion"); --no-bdd-cloud leaves them out
BDD_CLOUD = '--no-bdd-cloud' not in sys.argv

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

# Memory: the cell's RESERVATION in the queue's budget (D17.5); its limit is
# the queue's, V5's class (run.sh: --limit-rss 32768 --memory-floor 2000). A JVM engine (BDD-APKeep,
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
# --- from zero only (D17.10) ----------------------------------------------
#: ad6 as V5 ran it: rank grounding, cadical195; wl_i2 answers only under
#: flow grounding (V5 +F, results_v5_i2_ad6_flow_20261008)
AD6 = {w: {'ad6-grounding': 'rank', 'ad6-solver': 'cadical195'} for w in GRID}
AD6['wl_i2'] = {'ad6-grounding': 'flow', 'ad6-solver': 'cadical195'}
#: V5's from-zero cost where it has one (RESULTS.md section 2), else the cap
AD6_H = {'wl_airtel1': 0.01, 'wl_airtel2': 0.01, 'wl_cloud': 0.02, 'wl_up': 0.12,
         'wl_stanford': 0.22, 'wl_i2': 1.06}
#: ad6's from-zero peaks in V5 go to 14 GB (wl_up): a JVM-sized reservation
AD6_MB = 18432


def add_z(name, workload_dir, e, est_h, mem_mb, **kw):
    cell = {'name': name, 'workload': workload_dir, 'engine': e, 'stream': 'z',
            'mem_mb': mem_mb, 'limit-wall': CAP_S, 'est_h': est_h}
    cell.update(kw)
    cells.append(cell)


for w in GRID:
    d, extra = WL[w]
    add_z('Z_%s_ad6' % w, d, 'ad6', AD6_H.get(w, CAP_S / 3600), AD6_MB,
          **dict(extra, **AD6[w]))
# BDD-APKeep on wl_stanford and wl_i2: recorded, not run (owner, 2026-10-19)
for w in ('wl_stanford', 'wl_i2'):
    d, extra = WL[w]
    add_z('Z_%s_apkeep' % w, d, 'apkeep', 0, 0, recorded={
        'outcome': 'did_not_finish', 'limit_tripped': 'wall', 'limit_wall_s': CAP_S,
        'basis': "V5: no answer within 24 h (RESULTS.md section 1); the cap is 12 h "
                 "(INCREMENTAL_PLAN.md D17.10)"}, **extra)

# the wl_berkeley series, from zero only, its inputs generated once per size
# into this directory (bench/campaign_inputs.py berkeley)
BERKELEY = ('netplumber', 'veriflow', 'apkeep', 'ndd-apkeep', 'ad6')
#: V5's numbers where it has them (RESULTS.md section 4; NDD-APKeep's k=30 from
#: the 2026-10-19 check), else the cap, so an unknown cell starts early
BERK_H = {('netplumber', 30): 0.06, ('netplumber', 10): 0.86, ('apkeep', 3): 0.22,
          ('ndd-apkeep', 30): 0.23}
BERK_MB = {'netplumber': {30: 4096, 10: 10240, 3: 30720}}
for k in (30, 10, 3):
    for e in BERKELEY:
        mb = BERK_MB.get(e, {}).get(k) or (18432 if k == 30 else 30720)
        add_z('Z_wl_berkeley_k%d_%s' % (k, e),
              'bench/campaigns/results_inc_dev_d16_fave_20261017/inputs/wl_berkeley_k%d' % k,
              e, BERK_H.get((e, k), CAP_S / 3600), mb,
              **({'ad6-grounding': 'rank', 'ad6-solver': 'cadical195'} if e == 'ad6' else {}))
# k = 1: once per engine, alone, the machine's memory (owner, 2026-10-19)
for e in BERKELEY:
    add_z('Z_wl_berkeley_k1_%s' % e,
          'bench/campaigns/results_inc_dev_d16_fave_20261017/inputs/wl_berkeley_k1',
          # alone, the memory AVAILABLE at its start less the 2 GB V5's floor
          # keeps free is the cell's own limit: its stop is a MEMORY stop, not
          # a machine stop (no floor: nothing else runs). The machine's RAM
          # less 2 GB let the OOM killer come first in the k = 1 trial
          # (results_ndd_berkeley_k1_trial_20261020/FINDINGS.txt).
          e, CAP_S / 3600, 0, alone=True,
          **{'limit-rss-margin': 2048, 'memory-floor': 0},
          **({'ad6-grounding': 'rank', 'ad6-solver': 'cadical195'} if e == 'ad6' else {}))

# declared violation counts (V5 declared these, D17.6)
for c in cells:
    if c['workload'] in ('bench/wl_airtel1', 'bench/wl_airtel2'):
        c['expect-violations'] = 0

cells.sort(key=lambda c: -c['est_h'])               # longest first
with open(OUT, 'w') as out:
    json.dump(cells, out, indent=1)

# --- the contention sample (D17.8): from zero, serial, unpinned ----------------
contention = [dict(c, name=c['name'].replace('Z_', 'K_', 1)) for c in cells
              if c['stream'] == 'z' and c['name'] == 'Z_%s_ad6' % 'wl_airtel1'] + [
    {'name': 'K_%s_%s' % (w, e), 'workload': WL[w][0], 'engine': e, 'stream': 'z',
     'mem_mb': 0, 'limit-wall': CAP_S, 'est_h': 0, **WL[w][1]}
    for w in ('wl_airtel1', 'wl_up') for e in ENGINES]
contention += [dict(c, name='K_wl_up_ad6') for c in cells if c['name'] == 'Z_wl_up_ad6']
with open(os.path.join(HERE, 'contention_queue.json'), 'w') as out:
    json.dump(contention, out, indent=1)

# --- the bridge (D17.4): V5's live layout on the same inputs, cell_queue.py ----
V5_BACKEND = {'netplumber': {'backend': 'netplumber'}, 'veriflow': {'backend': 'veriflow'},
              'apkeep': {'backend': 'apkeep', 'apkeep-engine': 'bdd'},
              'ndd-apkeep': {'backend': 'apkeep', 'apkeep-engine': 'ndd-apkeep'},
              'ad6': {'backend': 'ad6'}}
bridge = []
for w in GRID:
    for e in ENGINES + ('ad6',):
        if (w, e) in NO_CELL:
            continue
        cell = {'name': 'bridge_%s_%s' % (w, e), 'workload': w, **V5_BACKEND[e],
                'limit-class': 'dev', 'limit-wall': CAP_S, 'limit-rss': 32768,
                'memory-floor': 2000, 'status-every': 60,
                'reuse-inputs': True, 'no-anomalies': True}
        if e == 'ad6':
            cell['engine-options'] = '--grounding %s --solver %s' % (
                AD6[w]['ad6-grounding'], AD6[w]['ad6-solver'])
        if w in ('wl_airtel1', 'wl_airtel2'):
            cell['expect-violations'] = 0
        bridge.append(cell)
with open(os.path.join(HERE, 'bridge_queue.json'), 'w') as out:
    json.dump(bridge, out, indent=1)
print('contention %d cells, bridge %d cells' % (len(contention), len(bridge)))
by = {}
for c in cells:
    by[c['name'][0]] = by.get(c['name'][0], 0) + 1
print('%d cells %s, %.0f estimated cell-hours (capped)' % (len(cells), dict(sorted(by.items())), sum(c['est_h'] for c in cells)))
