"""The calibration through FaVe before the D16 indicative run
(INCREMENTAL_PLAN.md D14, D15, D16): the first 50 updates of every cell kind
of the grid, to size memory limits and ground the run's predictions. Writes
queue.json. Run from fave/: python3 <this> [vf_tum_mem_mb]."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'queue.json')
#: VeriFlow-FR on wl_tum: 1.3x the peak of the full wl_tum incremental run
#: (TODO item 59), given at declaration
VF_TUM_MB = int(sys.argv[1]) if len(sys.argv) > 1 else None

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
GRID = tuple(WL)                                  # D13 as cut by D15
ENGINES = ('netplumber', 'veriflow', 'apkeep', 'ndd-apkeep')
NO_CELL = {('wl_stanford', 'apkeep'), ('wl_i2', 'apkeep')}     # D13
S4_WL = ('wl_cloud', 'wl_up', 'wl_tum')
FOOTPRINTED = ('veriflow', 'apkeep', 'ndd-apkeep')
#: builds measured in hours: one cell (S2) each, enough for its build, its
#: first check and a per-update rate -- BDD-APKeep on wl_cloud (3.24 h from
#: zero in V5), VeriFlow-FR on wl_tum (its checks with tracking on: TODO 59)
ONE_CELL = {('wl_cloud', 'apkeep'), ('wl_tum', 'veriflow')}
CAP_S = 12 * 3600                                 # D16
N = 50

def mem(w, e):
    if (w, e) == ('wl_tum', 'veriflow') and VF_TUM_MB:
        return VF_TUM_MB
    return {'ndd-apkeep': 16384, 'apkeep': 12288}.get(e, 8192)

cells = []
def add(name, w, e, s, **kw):
    d, extra = WL[w]
    cell = {'name': name, 'workload': d, 'engine': e, 'stream': s,
            'mem_mb': mem(w, e), 'limit-wall': CAP_S, 'limit-updates': N,
            # longest first: the hour-long builds, then the rest
            'est_h': 6.0 if (w, e) in ONE_CELL else 0.5}
    cell.update(extra)
    cell.update(kw)
    cells.append(cell)

for w in GRID:
    for e in ENGINES:
        if (w, e) in NO_CELL:
            continue
        streams = ('s2',) if (w, e) in ONE_CELL else ('s1', 's2', 's3')
        for s in streams:                           # A: default footprint
            add('A_%s_%s_%s' % (w, e, s), w, e, s)
        if (w, e) in ONE_CELL:
            continue
        if e in FOOTPRINTED:                        # D: coarse
            for s in ('s1', 's2', 's3'):
                add('D_%s_%s_%s_coarse' % (w, e, s), w, e, s, footprint='coarse')
        if w in S4_WL:                              # C: S4
            add('C_%s_%s_s4' % (w, e), w, e, 's4')
with open(OUT, 'w') as out:
    json.dump(cells, out, indent=1)
print('%d cells' % len(cells))
