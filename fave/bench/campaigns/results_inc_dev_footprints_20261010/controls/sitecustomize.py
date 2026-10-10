# Experiment hook (port-order check): point lib_apkeep at a scratch jar, in memory only.
import os, sys
_sys = '/usr/lib/python3.12/sitecustomize.py'
if os.path.exists(_sys):
    exec(compile(open(_sys).read(), _sys, 'exec'))
_jar = os.environ.get('FAVE_EXP_APKEEP_JAR')
if _jar:
    try:
        import apkeep.lib_apkeep as _l
        _l._APKEEP_JAR = _jar
        with open(os.environ['FAVE_EXP_LOG'], 'a') as f:
            f.write('%d %s -> %s\n' % (os.getpid(), _l.__file__, _jar))
    except ImportError as ex:
        with open(os.environ['FAVE_EXP_LOG'], 'a') as f:
            f.write('%d import failed: %s\n' % (os.getpid(), ex))
