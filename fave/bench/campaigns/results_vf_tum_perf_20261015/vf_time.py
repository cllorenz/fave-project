""" wl_tum's 8,497 checks on VeriFlow-FR in-process (tracking off), timed apart
from the build; per check verdicts written. Run from a tree's fave/ with
PYTHONPATH=. argv: verdicts.json """
import json, os, resource, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
import veriflow.adapter as vfa
engine = make_engine('veriflow')()
checks = inc.load_checks('bench/wl_tum/checks.json')
with InProcessFaVe(engine) as fave:
    t0 = time.perf_counter()
    fave.replay('bench/wl_tum')
    t1 = time.perf_counter()
    verdicts = inc.VerdictCache(fave, engine, checks).full()
    t2 = time.perf_counter()
json.dump(verdicts, open(sys.argv[1], 'w'))
print(json.dumps({'adapter': vfa.__file__, 'lib': vfa.libveriflow_fr.__file__,
                  'early_exit_env': os.environ.get('FAVE_VF_EARLY_EXIT'),
                  'replay_s': round(t1 - t0, 1), 'checks_s': round(t2 - t1, 1),
                  'checks': len(verdicts), 'violated': sum(verdicts.values()),
                  'early_exits': getattr(engine, 'early_exits', None),
                  'walks': len(engine.work), 'local_ecs': sum(w[1] for w in engine.work),
                  'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}))
