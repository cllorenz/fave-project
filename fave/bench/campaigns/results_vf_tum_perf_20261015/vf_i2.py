""" TODO item 59, option c on wl_i2, where the state rule's memory saves work
(0.94 M local ECs against path's 1.93 M): its all-pairs matrix on VeriFlow-FR,
tracking on (whole walks, merged footprints) as in the incremental regime.
argv: cache. Prints seconds, local ECs, states expanded, reachable pairs,
peak RSS. Run from fave/. """
import json, logging, resource, sys, time
sys.path.insert(0, '.')
from util.in_process_driver import InProcessFaVe
from veriflow.adapter import VeriFlowAdapter
cache = int(sys.argv[1])
eng = VeriFlowAdapter(logging.getLogger('i2'), state_cache=cache)
eng.track_affected(True)
with InProcessFaVe(eng) as fave:
    fave.replay('bench/wl_i2/i2-json',
                files={'topology': 'device_topology.json', 'policies': 'probes.json'})
    sources = sorted(g.node for g in eng._generators)
    probes = sorted(p.node for p in eng._probes)
    t = time.perf_counter()
    fave.check_compliance({p: [[s, False, []] for s in sources] for p in probes})
    s = time.perf_counter() - t
missed = {(r[0], r[1]) for r in eng.get_compliance_results()}
print(json.dumps({'state_cache': cache, 's': round(s, 1),
                  'local_ecs': sum(w[1] for w in eng.work), 'walks': len(eng.work),
                  'states': sum(w[2] for w in eng.work),
                  'reachable': len(sources) * len(probes) - len(missed),
                  'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}))
