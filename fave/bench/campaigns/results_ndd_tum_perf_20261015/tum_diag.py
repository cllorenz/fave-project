""" wl_tum's checks on BDD- or NDD-APKeep, per check: answer, traversal counts
(nodes visited, branches explored), time; and the atom counts. Run from fave/
with PYTHONPATH=. -- argv: engine out.jsonl """
import json, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
import jpype

engine_name, out_path = sys.argv[1], sys.argv[2]
engine = make_engine(engine_name)()
checks = inc.load_checks('bench/wl_tum/checks.json')
rows = []
with InProcessFaVe(engine) as fave:
    fave.replay('bench/wl_tum')
    t0 = time.perf_counter()
    engine._build()
    build_s = time.perf_counter() - t0
    lib = engine._lib
    cls = jpype.JClass('apkeep.ndd.NddReachabilityChecker' if engine_name == 'ndd-apkeep'
                       else 'apkeep.checker.ReachabilityChecker')
    real = lib.is_reachable

    def wrapped(*a, **k):
        t = time.perf_counter()
        ans = real(*a, **k)
        rows.append({'src': '%s.%s' % (a[0], a[1]), 'dst': '%s.%s' % (a[2], a[3]),
                     'cond': bool(k.get('conditions')), 'related': k.get('related'),
                     'answer': bool(ans), 'nodes': int(cls.nodesVisited),
                     'branches': int(cls.branchesExplored),
                     's': time.perf_counter() - t})
        return ans
    lib.is_reachable = wrapped
    t0 = time.perf_counter()
    verdicts = inc.VerdictCache(fave, engine, checks).full()
    checks_s = time.perf_counter() - t0
    net = lib._net
    summary = {'engine': engine_name, 'build_s': round(build_s, 1),
               'checks_s': round(checks_s, 1), 'violated': sum(verdicts.values()),
               'queries': len(rows), 'ap_num': int(net.getAPNum()),
               'nodes': sum(r['nodes'] for r in rows),
               'branches': sum(r['branches'] for r in rows),
               'query_s': round(sum(r['s'] for r in rows), 1)}
    if engine_name == 'ndd-apkeep':
        A = jpype.JClass('org.ants.jndd.diagram.AtomizedNDD')
        summary['atoms_per_field'] = [int(A.getAllAtoms(f).size())
                                      for f in range(int(A.getFieldNum()) + 1)]
        summary['atomized_table'] = int(A.tableSize())
with open(out_path, 'w') as out:
    for r in rows:
        out.write(json.dumps(r) + '\n')
print(json.dumps(summary))
