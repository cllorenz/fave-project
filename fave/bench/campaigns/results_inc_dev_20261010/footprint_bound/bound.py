"""What a finer VeriFlow-FR footprint could save at best
(docs/VERIFLOW_FOOTPRINT_SCOPE.md §3), from this calibration's raw records.

Derived 2026-10-11, after the fact; the records predate the `-o` fix
(10b74417), so this is an upper-bound estimate, not a result. Columns, per
cell and summed over its stream:
  rechk     checks re-asked (the record's `rechecked`)
  changed   check lines whose verdict changed
  srcs      sources marked affected (one walk each)
  srcs_chg  sources with at least one changed check: the fewest walks any
            sound source-granular footprint can do
  chk|src   the checks of those sources: the fewest re-checks a sound
            footprint can report while re-checks stay per source
  t_upd_s, t_rchk_s  summed update and re-check time
"""
import glob, gzip, json, os, re
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cells")
src_re = re.compile(r's=(\S+)')
print('%-11s %-10s %-3s %8s %8s %8s %8s %8s %9s %9s' % (
    'workload', 'engine', 's', 'rechk', 'changed', 'srcs', 'srcs_chg', 'chk|src', 't_upd_s', 't_rchk_s'))
for cell in sorted(glob.glob(root + '/*')):
    wl, eng, s = re.match(r'(wl_\w+?)_(\w+)_(s\d)$', os.path.basename(cell)).groups()
    f = glob.glob(cell + '/rep01/updates.jsonl.gz')
    if not f:
        continue
    head = json.load(open(cell + '/rep01/head.json'))
    per_src = {}
    for c in head.get('initial_verdicts') or {}:
        m = src_re.search(c)
        if m:
            per_src[m.group(1)] = per_src.get(m.group(1), 0) + 1
    R = C = S = SC = CS = 0
    tu = tr = 0.0
    for line in gzip.open(f[0], 'rt'):
        d = json.loads(line)
        R += d['rechecked']
        C += len(d['changed'])
        srcs = {a for a, _p in d['affected']}
        chsrc = {src_re.search(c[0]).group(1) for c in d['changed']}
        S += len(srcs)
        SC += len(chsrc)
        CS += sum(per_src.get(x, 0) for x in chsrc)
        tu += d['t_update_s']
        tr += d['t_recheck_s']
    print('%-11s %-10s %-3s %8d %8d %8d %8d %8d %9.2f %9.2f' % (wl, eng, s, R, C, S, SC, CS, tu, tr))
