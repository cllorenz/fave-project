""" TODO item 59: wl_tum's 8,497 checks on VeriFlow-FR in the INCREMENTAL
regime's build -- tracking on (whole walks, merged footprints and witnesses
kept for every check), the default state cache. Does the whole run fit?
argv: verdicts.json. Run from fave/. """
import json, resource, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
engine = make_engine('veriflow')()
engine.track_affected(True)
checks = inc.load_checks('bench/wl_tum/checks.json')
with InProcessFaVe(engine) as fave:
    t0 = time.perf_counter()
    fave.replay('bench/wl_tum')
    t1 = time.perf_counter()
    verdicts = inc.VerdictCache(fave, engine, checks).full()
    t2 = time.perf_counter()
json.dump(verdicts, open(sys.argv[1], 'w'))
boxes = sum(fp.states() for fp in engine._footprints.values())
print(json.dumps({'tracking': True, 'state_cache': engine.state_cache,
                  'early_exit_applied': engine.early_exits,
                  'replay_s': round(t1 - t0, 1), 'checks_s': round(t2 - t1, 1),
                  'checks': len(verdicts), 'violated': sum(verdicts.values()),
                  'walks': len(engine.work), 'local_ecs': sum(w[1] for w in engine.work),
                  'footprints': len(engine._footprints), 'footprint_boxes': boxes,
                  'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}))
