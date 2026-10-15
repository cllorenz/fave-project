""" wl_tum's 8,497 checks on VeriFlow-FR in-process (the default footprint,
tracking off), with every walk recorded: query set, starts, local ECs, hops,
top tables, seconds; and every (re)build. Run from fave/ with PYTHONPATH=.
argv: out.jsonl """
import json, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe

out_path = sys.argv[1]
engine = make_engine('veriflow')()
walks, builds = [], []


class Timed:
    def __init__(self, net):
        self._net = net

    def __getattr__(self, name):
        return getattr(self._net, name)

    def local_deliveries(self, qs, starts, *rest):
        t = time.perf_counter()
        walked = self._net.local_deliveries(qs, starts, *rest)
        s = time.perf_counter() - t
        (answers, finished, stopped_at, predicted, single, local_ecs, hops,
         per_table) = walked[:8]
        top = sorted(per_table.items(), key=lambda kv: -kv[1])[:3]
        walks.append({'qs': qs, 'starts': len(starts), 'finished': bool(finished),
                      'local_ecs': local_ecs, 'hops': hops, 'top': top, 's': s})
        if len(walks) % 200 == 0:
            print('walks %d, %.0f s in walks' % (len(walks), sum(w['s'] for w in walks)),
                  file=sys.stderr, flush=True)
        return walked


real_build = engine.build


def build(extra_fields=()):
    before = engine.net
    t = time.perf_counter()
    real_build(extra_fields)
    if engine.net is not before and not isinstance(engine.net, Timed):
        builds.append({'fields': sorted(extra_fields), 's': time.perf_counter() - t})
        engine.net = Timed(engine.net)
engine.build = build

checks = inc.load_checks('bench/wl_tum/checks.json')
with InProcessFaVe(engine) as fave:
    t0 = time.perf_counter()
    fave.replay('bench/wl_tum')
    t1 = time.perf_counter()
    verdicts = inc.VerdictCache(fave, engine, checks).full()
    t2 = time.perf_counter()
with open(out_path, 'w') as out:
    for w in walks:
        out.write(json.dumps(w, default=str) + '\n')
print(json.dumps({'engine': 'veriflow', 'footprint': list(engine.footprint),
                  'replay_s': round(t1 - t0, 1), 'checks_s': round(t2 - t1, 1),
                  'violated': sum(verdicts.values()), 'walks': len(walks),
                  'walks_s': round(sum(w['s'] for w in walks), 1),
                  'builds': builds, 'unfinished': sum(not w['finished'] for w in walks)}))
