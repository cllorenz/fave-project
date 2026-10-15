""" One VeriFlow-FR walk of wl_tum alone: the costliest (source.vlan109 ->
probe.internet). argv: state|path. Prints seconds, local ECs, hops, peak RSS,
and the delivered tables. """
import json, resource, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
from rule.rule_model import RuleField
mode = sys.argv[1]
eng = make_engine('veriflow')()
with InProcessFaVe(eng) as fave:
    fave.replay('bench/wl_tum')
    eng.build(['related'])
    ir = eng.ir
    c = [c for c in inc.load_checks('bench/wl_tum/checks.json')
         if c.source == 'source.vlan109' and c.probe == 'probe.internet'][0]
    starts, sets = ir.generators[c.source]
    qss = [qs for b in sets for qs in eng.condition_sets(ir, b, [RuleField.from_json(f) for f in c.cond])]
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t = time.perf_counter()
    for qs in qss:
        w = eng.net.local_deliveries(qs, list(starts), eng.budget, mode == 'state', eng._scan, False, False)
    s = time.perf_counter() - t
    names = {v: k for k, v in ir.tables.items()}
    print(json.dumps({'mode': mode, 'check': c.line, 'sets': len(qss), 'starts': len(starts),
                      's': round(s, 1), 'finished': w[1], 'local_ecs': w[5], 'hops': w[6],
                      'budget': eng.budget, 'rss_before_mb': rss0 // 1024,
                      'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
                      'probe_reached': ir.probes[c.probe] in set(w[0][0]),
                      'delivered': sorted(names.get(t, str(t)) for t in w[0][0])}))
