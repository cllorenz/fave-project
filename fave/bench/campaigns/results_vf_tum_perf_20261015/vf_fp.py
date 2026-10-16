""" TODO item 59, step 1: what a VeriFlow-FR footprint costs on wl_tum. One
outbound walk (a source's unconditioned check to probe.internet), alone, with
the footprint recorded or not (argv: source, on|off). Prints seconds, local
ECs, states expanded, footprint states and boxes, peak RSS. Run from fave/. """
import json, resource, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
from rule.rule_model import RuleField
source, mode = sys.argv[1], sys.argv[2]
eng = make_engine('veriflow')()
with InProcessFaVe(eng) as fave:
    fave.replay('bench/wl_tum')
    eng.build(['related'])
    ir = eng.ir
    c = [c for c in inc.load_checks('bench/wl_tum/checks.json')
         if c.source == source and c.probe == 'probe.internet'][0]
    starts, sets = ir.generators[c.source]
    qss = [qs for b in sets for qs in eng.condition_sets(ir, b, [RuleField.from_json(f) for f in c.cond])]
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t = time.perf_counter()
    fp_states = 0
    for qs in qss:
        w = eng.net.local_deliveries(qs, list(starts), 0, True, eng._scan, mode == 'on', False)
        if mode == 'on':
            fp_states += w[8].states()  # boxes once merged (item 59)
    s = time.perf_counter() - t
    print(json.dumps({'check': c.line, 'footprint': mode, 'sets': len(qss), 's': round(s, 1),
                      'finished': w[1], 'local_ecs': w[5], 'hops': w[6],
                      'footprint_states': fp_states if mode == 'on' else None,
                      'rss_before_mb': rss0 // 1024,
                      'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}))
