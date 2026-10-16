""" TODO item 59, option c: one wl_tum outbound walk alone under the state rule
with a bounded explored-state cache, footprint recorded (merged) as in the
incremental regime. argv: source, cache (0 = unbounded). Run from fave/. """
import json, resource, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
from rule.rule_model import RuleField
source, cache = sys.argv[1], int(sys.argv[2])
eng = make_engine('veriflow')()
with InProcessFaVe(eng) as fave:
    fave.replay('bench/wl_tum')
    eng.build(['related'])
    ir = eng.ir
    c = [c for c in inc.load_checks('bench/wl_tum/checks.json')
         if c.source == source and c.probe == 'probe.internet'][0]
    starts, sets = ir.generators[c.source]
    qss = [qs for b in sets for qs in eng.condition_sets(ir, b, [RuleField.from_json(f) for f in c.cond])]
    t = time.perf_counter()
    for qs in qss:
        w = eng.net.local_deliveries(qs, list(starts), 0, True, eng._scan, True, True, [], cache)
    s = time.perf_counter() - t
    names = {v: k for k, v in ir.tables.items()}
    print(json.dumps({'check': c.line, 'state_cache': cache, 's': round(s, 1), 'finished': w[1],
                      'local_ecs': w[5], 'hops': w[6], 'footprint_boxes': w[8].states(),
                      'delivered': len(w[0][0]),
                      'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}))
