"""The D11 grid as an incremental_queue.py queue (INCREMENTAL_PLAN.md D11, D13,
§7 ablation, O3.3 oracle subset). Writes queue.json; est_h comes from
projections.json (made by project.py from the dev records), mem_mb from the
table below. Run from fave/."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'queue.json')

# workload -> (directory, extra cell args)
WL = {
    'wl_example': ('bench/wl_example', {}),
    'wl_ifi': ('bench/wl_ifi', {}),
    'wl_cloud': ('bench/wl_cloud', {}),
    'wl_airtel1': ('bench/wl_airtel1', {}),
    'wl_airtel2': ('bench/wl_airtel2', {}),
    'wl_up': ('bench/wl_up', {}),
    'wl_stanford': ('bench/wl_stanford/stanford-json',
                    {'checks': '../checks.json', 'files': 'topology=device_topology.json,policies=probes.json'}),
    'wl_i2': ('bench/wl_i2/i2-json',
              {'checks': '../checks.json', 'files': 'topology=device_topology.json,policies=probes.json'}),
    'wl_tum': ('bench/wl_tum', {}),
}
GRID = ('wl_example', 'wl_ifi', 'wl_cloud', 'wl_airtel1', 'wl_airtel2', 'wl_up', 'wl_stanford', 'wl_i2')
ENGINES = ('netplumber', 'veriflow', 'apkeep', 'ndd-apkeep')
NO_CELL = {('wl_stanford', 'apkeep'), ('wl_i2', 'apkeep')}     # from-zero DNF in V5 (D13)
S4_WL = ('wl_ifi', 'wl_cloud', 'wl_up', 'wl_tum')
# builds longer than the cap: BDD-APKeep on wl_cloud took 3.24 h from zero in V5
# (RESULTS.md §3), so a 2 h cell would record no update. Its A cells get a longer
# cap; its B, C, D and E cells are left out (declared in PROTOCOL.txt)
LONG_BUILD = {('wl_cloud', 'apkeep'): 6.0}

# memory per cell (MB), which is also its RSS limit: 1.3x the largest peak RSS a
# dev cell of the workload x engine reached (peaks.json), an oracle cell 1.6x
# the plain peak when no oracle cell was recorded (it builds a second network
# from zero); with no record, 12 GB for NDD-APKeep (its tables alone reach
# 10-16 GB) and 4 GB otherwise; at least 2 GB, rounded up to whole GB
PEAKS = {}
kp = os.path.join(HERE, 'peaks.json')
if os.path.exists(kp):
    with open(kp) as raw:
        PEAKS = {tuple(k.split('|')): v for k, v in json.load(raw).items()}

def mem(w, e, oracle=False):
    plain = PEAKS.get((w, e, 'plain'))
    seen = PEAKS.get((w, e, 'oracle')) if oracle else plain
    if seen:
        mb = 1.3 * seen
    elif oracle and plain:
        mb = 1.6 * plain
    else:
        mb = {'ndd-apkeep': 12288, 'apkeep': 8192}.get(e, 4096)
    return int(-(-max(mb, 2048) // 1024) * 1024)

CAP_H = 2.0          # limit-wall per cell (7200 s, as in the calibration)
PROJ = {}
pp = os.path.join(HERE, 'projections.json')
if os.path.exists(pp):
    with open(pp) as raw:
        PROJ = {tuple(k.split('|')): v for k, v in json.load(raw).items()}

RATES = {}
rp = os.path.join(HERE, 'rates.json')
if os.path.exists(rp):
    with open(rp) as raw:
        RATES = {tuple(k.split('|')): v for k, v in json.load(raw).items()}

def every(w, e, s, default):
    """ The oracle's full-checkpoint spacing: about three checkpoints inside
    the wall cap (each also builds the network from zero), never more often
    than every update nor less often than `default`. """
    r = RATES.get((w, e, s, 'default'))
    if not r or r['mean_s'] <= 0:
        return default
    n_cap = max(0.0, CAP_H * 3600 - 4 * r['build_s']) / r['mean_s']
    return int(max(1, min(default, n_cap // 3)))

def est(w, e, s, mode):
    # no dev record yet: assume the wall cap, so the unknown cell is scheduled early
    return PROJ.get((w, e, s, mode), PROJ.get((w, e, s, 'default'), CAP_H))

cells = []
def add(name, w, e, s, **kw):
    d, extra = WL[w]
    cap = LONG_BUILD.get((w, e))
    if cap and not name.startswith('A_'):
        return
    cell = {'name': name, 'workload': d, 'engine': e, 'stream': s,
            'mem_mb': mem(w, e, 'oracle-sample' in kw),
            'limit-wall': int((cap or CAP_H) * 3600)}
    if cap:
        kw['est_h'] = cap
    cell.update(extra)
    cell.update(kw)
    cells.append(cell)

DEFAULT = {'apkeep': 'witness,dead-ends', 'ndd-apkeep': 'witness,dead-ends', 'veriflow': 'coarse'}
for w in GRID:
    for e in ENGINES:
        if (w, e) in NO_CELL:
            continue
        fp = DEFAULT.get(e)
        fpk = {'footprint': fp} if fp else {}
        for s in ('s1', 's2', 's3'):                       # A
            add('A_%s_%s_%s' % (w, e, s), w, e, s, est_h=est(w, e, s, 'default'), **fpk)
        for b in (10, 100, 0):                             # B (0: the whole stream)
            add('B_%s_%s_s2_b%s' % (w, e, b or 'all'), w, e, 's2',
                batch=(b or 10 ** 9), est_h=est(w, e, 's2', 'default'), **fpk)
        add('E_%s_%s_s2_oracle' % (w, e), w, e, 's2', est_h=2 * est(w, e, 's2', 'default'),
            **{'oracle-sample': 50, 'oracle-every': every(w, e, 's2', 1000)}, **fpk)
for e in ENGINES:                                          # A': wl_tum, updates only
    for s in ('s1', 's2', 's3'):
        add('A_wl_tum_%s_%s' % (e, s), 'wl_tum', e, s, est_h=est('wl_tum', e, s, 'default'),
            **({'footprint': DEFAULT[e]} if e in DEFAULT else {}))
for w in S4_WL:                                            # C
    for e in ENGINES:
        add('C_%s_%s_s4' % (w, e), w, e, 's4', est_h=est(w, e, 's4', 'default'),
            **{'limit-updates': 1000}, **({'footprint': DEFAULT[e]} if e in DEFAULT else {}))
        if w != 'wl_tum':
            add('E_%s_%s_s4_oracle' % (w, e), w, e, 's4', est_h=2 * est(w, e, 's4', 'default'),
                **{'limit-updates': 1000, 'oracle-sample': 50, 'oracle-every': every(w, e, 's4', 250)},
                **({'footprint': DEFAULT[e]} if e in DEFAULT else {}))
ABL = {'apkeep': ('coarse', 'witness', 'dead-ends'), 'ndd-apkeep': ('coarse', 'witness', 'dead-ends'),
       'veriflow': ('witness', 'dead-ends', 'witness,dead-ends')}
for w in GRID:                                             # D: the ablation
    for e, modes in ABL.items():
        if (w, e) in NO_CELL:
            continue
        for m in modes:
            for s in ('s1', 's2', 's3'):
                add('D_%s_%s_%s_%s' % (w, e, s, m.replace(',', '+')), w, e, s,
                    footprint=m, est_h=est(w, e, s, m))
with open(OUT, 'w') as out:
    json.dump(cells, out, indent=1)
print('%d cells, %.0f estimated cell-hours' % (len(cells), sum(c['est_h'] for c in cells)))
