"""One (workload, engine, variant) of the structure-cost measurement, in a
process of its own, through FaVe (InProcessFaVe). Variants:
  plain      the from-zero structure (ingress classes, pass-through elision,
             IPv6 routers by their routes), check untracked -- V5's shape
  updatable  the update-ready structure (`_for_updates`), check untracked
  tracked    the update-ready structure, check tracked (footprints): today's
             incremental head
Prints one JSON line: replay, build (APKeep's lazy build, forced before the
check) and check seconds, element and rule counts, verdict count, peak RSS.
Run from fave/: python3 <this> <prefix> <checks> <engine> <variant>."""
import json, logging, sys, time
from apkeep.adapter import APKeepAdapter
from util.in_process_driver import InProcessFaVe
from util import incremental as inc

prefix, checks_path, engine, variant = sys.argv[1:5]
files = ({'topology': 'device_topology.json', 'policies': 'probes.json'}
         if prefix.endswith('-json') else None)
log = logging.getLogger('probe'); log.setLevel(logging.ERROR)
eng = APKeepAdapter(log, engine=engine)
counts = {}
orig = eng._translate
def counted():
    t = orig()
    counts.update(elements=len(t['fwd_devices']) + len(t['filter_devices'] or [])
                  + sum(len(v) for v in (t['device_acls'] or {}).values())
                  + sum(len(v) for v in (t['device_nats'] or {}).values()),
                  rules=len(t['rules']), edges=len(t['edges']))
    return t
eng._translate = counted
checks = inc.load_checks(checks_path)
t0 = time.perf_counter()
with InProcessFaVe(eng) as fave:
    fave.replay(prefix, files=files)
    t1 = time.perf_counter()
    if variant in ('updatable', 'tracked'):
        # what `_build` does when tracking is on before it, without tracking
        eng._for_updates = True
        eng._frozen_ipv6 |= eng._ipv6_fib_devices
    if variant == 'tracked':
        eng.track_affected(True)
    eng._build()
    t2 = time.perf_counter()
    cache = inc.VerdictCache(fave, eng, checks)
    cache.full()
    t3 = time.perf_counter()
hwm = int([l for l in open('/proc/self/status') if l.startswith('VmHWM')][0].split()[1]) / 1024
print(json.dumps({'workload': prefix, 'engine': engine, 'variant': variant,
                  'for_updates': eng._for_updates, 'replay_s': round(t1 - t0, 3),
                  'build_s': round(t2 - t1, 3), 'check_s': round(t3 - t2, 3),
                  'violated': sum(1 for v in cache.verdict.values() if v),
                  'checks': len(cache.verdict), 'peak_rss_mb': round(hwm),
                  'configuration': eng.configuration_stamp(), **counts}), flush=True)
