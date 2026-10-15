""" Which sources, fields and tables the costliest VeriFlow-FR walks on wl_tum
belong to. argv: vf_walks.jsonl """
import json, sys
from collections import Counter
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
from rule.rule_model import RuleField
W = [json.loads(l) for l in open(sys.argv[1])]
W.sort(key=lambda w: -w['s'])
eng = make_engine('veriflow')()
with InProcessFaVe(eng) as fave:
    fave.replay('bench/wl_tum')
    eng.build(['related'])
    ir = eng.ir
    print('fields', ir.fields)
    print('scan', eng._scan)
    names = {v: k for k, v in ir.tables.items()}
    owner = {}
    for c in inc.load_checks('bench/wl_tum/checks.json'):
        for base in ir.generators[c.source][1]:
            for qs in eng.condition_sets(ir, base, [RuleField.from_json(f) for f in c.cond]):
                owner.setdefault(qs, set()).add((c.source, c.line.split('&&', 2)[-1].strip()))
    def dec(qs):
        out, o = [], 0
        for n, w in ir.fields:
            b = qs[o:o + w]; o += w
            if set(b) != {'x'}:
                out.append('%s=%s' % (n, b))
        return out
    for w in W[:12]:
        print(round(w['s']), w['local_ecs'], w['hops'], dec(w['qs']), sorted(owner.get(w['qs'], []))[:3],
              [(names.get(t, t), n) for t, n in w['top']])
    src = Counter()
    for w in W:
        for s in {o[0] for o in owner.get(w['qs'], [])} or {'?'}:
            src[s] += w['s']
    print('by source', [(s, round(v)) for s, v in src.most_common(8)])
    per_table = Counter(r.table for r in ir.rules)
    print('rules', len(ir.rules), 'top tables', [(names.get(t, t), n) for t, n in per_table.most_common(6)])
    ecs = sum(w['local_ecs'] for w in W); print('local ECs total', ecs, 'per s', round(ecs / sum(w['s'] for w in W)))
