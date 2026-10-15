""" VeriFlow-FR wl_tum walk time split by check kind. argv: vf_walks.jsonl """
import json, sys
from collections import Counter, defaultdict
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
from rule.rule_model import RuleField
W = [json.loads(l) for l in open(sys.argv[1])]
eng = make_engine('veriflow')()
with InProcessFaVe(eng) as fave:
    fave.replay('bench/wl_tum')
    eng.build(['related'])
    ir = eng.ir
    kind = defaultdict(set)
    for c in inc.load_checks('bench/wl_tum/checks.json'):
        k = ('internet->' if c.source == 'source.internet' else 'vlan->') + \
            ('internet' if c.probe == 'probe.internet' else 'host/vlan')
        for b in ir.generators[c.source][1]:
            for qs in eng.condition_sets(ir, b, [RuleField.from_json(f) for f in c.cond]):
                kind[qs].add(k)
    t, n, e = Counter(), Counter(), Counter()
    seen = set(); first = Counter()
    for w in W:
        k = '+'.join(sorted(kind[w['qs']])) or '?'
        t[k] += w['s']; n[k] += 1; e[k] += w['local_ecs']
        if w['qs'] not in seen:
            seen.add(w['qs']); first[k] += w['s']
    tot = sum(t.values())
    for k in t:
        print('%-40s walks %5d  s %8.1f (%4.1f %%)  first-walk s %8.1f  local ECs %d'
              % (k, n[k], t[k], 100 * t[k] / tot, first[k], e[k]))
    print('total', round(tot, 1), 'first walks only', round(sum(first.values()), 1))
    sizes = sorted((w['s'] for w in W), reverse=True)
    print('walks > 10 s', sum(s > 10 for s in sizes), 'their s', round(sum(s for s in sizes if s > 10)),
          'walks > 1 s', sum(s > 1 for s in sizes))
