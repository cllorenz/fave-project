""" wl_tum's 8,497 checks on one engine, in-process: replay and checks timed
apart, tracking (footprints) on or off. Run from fave/ with PYTHONPATH=. """
import json, resource, sys, time
sys.path.insert(0, '.')
from bench.incremental_run import make_engine
from util import incremental as inc
from util.in_process_driver import InProcessFaVe

engine_name, track = sys.argv[1], sys.argv[2] == 'track'
import os
import apkeep.lib_apkeep as _la, apkeep.lib_ndd as _ln
if os.environ.get('VARIANT_APKEEP_JAR'):
    _la._APKEEP_JAR = os.environ['VARIANT_APKEEP_JAR']
variant = os.environ.get('VARIANT_NDD_JAR')
if variant:
    _la._NDD_JAR = variant
    if hasattr(_ln, '_NDD_JAR'):
        _ln._NDD_JAR = variant
if engine_name == 'ndd-flood':
    import logging
    from apkeep.adapter import APKeepAdapter
    engine = APKeepAdapter(logging.getLogger('x'), engine='ndd')
else:
    engine = make_engine(engine_name)()
engine.track_affected(track)
checks = inc.load_checks('bench/wl_tum/checks.json')
t0 = time.perf_counter()
with InProcessFaVe(engine) as fave:
    fave.replay('bench/wl_tum')
    t1 = time.perf_counter()
    if hasattr(engine, '_build'):
        engine._build()          # APKeep builds lazily; time it apart
    tb = time.perf_counter()
    if os.environ.get('VARIANT_C') == 'off':
        import jpype
        jpype.java.lang.System.setProperty('fave.variantC', 'false')
    cache = inc.VerdictCache(fave, engine, checks)
    verdicts = cache.full()
    t2 = time.perf_counter()
import jpype
loaded = str(jpype.JClass('org.ants.jndd.diagram.AtomizedNDD').class_
             .getProtectionDomain().getCodeSource().getLocation()) if 'ndd' in engine_name else None
ports_jar = str(jpype.JClass('apkeep.ndd.NddPorts').class_
             .getProtectionDomain().getCodeSource().getLocation()) if 'ndd' in engine_name else None
print(json.dumps({'engine': engine_name, 'track': track, 'checks': len(verdicts),
                  'violated': sum(verdicts.values()), 'rounds': len(inc._rounds(checks)),
                  'replay_s': round(t1 - t0, 1), 'build_s': round(tb - t1, 1), 'checks_s': round(t2 - tb, 1),
                  'ndd_jar': loaded, 'apkeep_jar': ports_jar, 'maxrss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}))
