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
allc = inc.load_checks('bench/wl_tum/checks.json')
checks = allc[2000:2200]
with InProcessFaVe(engine) as fave:
    fave.replay('bench/wl_tum')
    engine._build()
    out = []
    for i in range(3):
        t = time.perf_counter()
        inc.VerdictCache(fave, engine, checks).full()
        out.append(round(time.perf_counter() - t, 2))
    f = jpype.JClass('apkeep.ndd.NddPorts').class_.getDeclaredField('queryCache')
    f.setAccessible(True)
    print(json.dumps({'passes_s': out, 'queryCache_on': bool(f.get(None))}))
