"""tracemalloc attribution of FaVe's Python memory at three points of a
from-zero NDD-APKeep cell: end of load, after translation, after the build
(before the buffers are released). Dev probe; patches at runtime, nothing on disk."""
import collections, gc, json, os, sys, time, tracemalloc
sys.path.insert(0, '/home/ubuntu/fave-project/fave')
OUT = sys.argv[1]
tracemalloc.start(1)
from apkeep import adapter as A
from bench import incremental_run as R

def rss():
    with open('/proc/self/status') as h:
        for l in h:
            if l.startswith('VmRSS'): return int(l.split()[1]) // 1024

report = {}
def snap(tag):
    s = tracemalloc.take_snapshot()
    byfile = collections.Counter(); byline = collections.Counter()
    for st in s.statistics('lineno'):
        f = st.traceback[0].filename.replace('/home/ubuntu/fave-project/', '')
        byfile[f] += st.size; byline['%s:%d' % (f, st.traceback[0].lineno)] += st.size
    types = collections.Counter(type(o).__name__ for o in gc.get_objects())
    report[tag] = {'t': time.time(), 'rss_mb': rss(),
                   'traced_mb': tracemalloc.get_traced_memory()[0] / 2**20,
                   'peak_traced_mb': tracemalloc.get_traced_memory()[1] / 2**20,
                   'by_file_mb': {k: round(v / 2**20, 1) for k, v in byfile.most_common(25)},
                   'by_line_mb': {k: round(v / 2**20, 1) for k, v in byline.most_common(40)},
                   'gc_types': dict(types.most_common(25))}
    json.dump(report, open(OUT, 'w'), indent=1)
    print(tag, report[tag]['rss_mb'], round(report[tag]['traced_mb']), flush=True)

orig_t, orig_r = A.APKeepAdapter._translate, A.APKeepAdapter._release_build_buffers
def _translate(self):
    if 'load' not in report: snap('load')
    t = orig_t(self)
    if 'translated' not in report: snap('translated')
    return t
def _release(self):
    if 'built' not in report: snap('built')
    return orig_r(self)
A.APKeepAdapter._translate = _translate
A.APKeepAdapter._release_build_buffers = _release
R.main(sys.argv[2:])
