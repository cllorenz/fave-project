""" NDD-APKeep on wl_tum: collections and table size around the checks; the
first 600 queries only. Run from fave/ with PYTHONPATH=. """
import os, sys, time, json
sys.path.insert(0, '.')
import apkeep.lib_apkeep as la
if os.environ.get('VARIANT_APKEEP_JAR'):
    la._APKEEP_JAR = os.environ['VARIANT_APKEEP_JAR']
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe
import jpype
engine = make_engine('ndd-apkeep')()
checks = inc.load_checks('bench/wl_tum/checks.json')[:600]
with InProcessFaVe(engine) as fave:
    fave.replay('bench/wl_tum')
    engine._build()
    P = jpype.JClass('apkeep.ndd.NddPorts'); A = jpype.JClass('org.ants.jndd.diagram.AtomizedNDD')
    c0, s0 = int(P.collections), int(A.tableSize())
    t = time.perf_counter()
    inc.VerdictCache(fave, engine, checks).full()
    print(json.dumps({'queries': 600, 's': round(time.perf_counter() - t, 1),
                      'collections': int(P.collections) - c0, 'table_before': s0,
                      'table_after': int(A.tableSize()),
                      'floor': int(P.COLLECT_FLOOR)}))
