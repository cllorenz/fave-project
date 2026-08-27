"""Axis 2 (AD6_ENCODING_PLAN.md §3/§2.3): ad6's own hand-rolled per-bit
propositional encoding vs. a native Z3 QF_BV (bitvector theory) model of
the exact same LPM-forwarding decision problem -- same logical question
(does some destination address exist that is admitted hop-by-hop through
to ACCEPT), two different modeling layers. Not a toy: the Z3 model
encodes the SAME R distractor-prefix exclusions per hop ad6's own ruleset
carries, so both sides reason about an equally-sized rule set.

Usage: PYTHONPATH=../ad6 python3 axis2_smt.py [n_routers] [distractors_per_router]
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

import z3

from gen_topology import (
    DEST_PREFIX, FORWARD_PREFIX, _distractor_prefix,
)


def _cidr_to_bits(cidr):
    addr, plen = cidr.split('/')
    plen = int(plen)
    # reuse ad6's own address parsing convention: 8 groups of 16 bits
    groups = addr.split('::')
    if len(groups) == 2:
        left = groups[0].split(':') if groups[0] else []
        right = groups[1].split(':') if groups[1] else []
        groups = left + ['0'] * (8 - len(left) - len(right)) + right
    else:
        groups = addr.split(':')
    value = 0
    for g in groups:
        value = (value << 16) | int(g, 16)
    return value, plen


def _prefix_matches(dst, cidr):
    value, plen = _cidr_to_bits(cidr)
    if plen == 0:
        return z3.BoolVal(True)
    return z3.Extract(127, 128 - plen, dst) == z3.BitVecVal(value >> (128 - plen), plen)


def build_z3_query(n_routers, distractors_per_router):
    dst = z3.BitVec('dst', 128)
    admitted = z3.BoolVal(True)

    for i in range(1, n_routers + 1):
        not_distractor = z3.And(*[
            z3.Not(_prefix_matches(dst, _distractor_prefix(i, d)))
            for d in range(distractors_per_router)
        ]) if distractors_per_router else z3.BoolVal(True)

        if i == n_routers:
            hop_admits = z3.And(not_distractor, _prefix_matches(dst, DEST_PREFIX))
        else:
            hop_admits = z3.And(not_distractor, _prefix_matches(dst, FORWARD_PREFIX))

        admitted = z3.And(admitted, hop_admits)

    return dst, admitted


def run(n_routers, distractors_per_router):
    t0 = time.perf_counter()
    dst, admitted = build_z3_query(n_routers, distractors_per_router)
    solver = z3.Solver()
    solver.add(admitted)
    build_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = solver.check()
    solve_time = time.perf_counter() - t1

    return {
        'n_routers': n_routers, 'distractors_per_router': distractors_per_router,
        'z3_build_time': build_time, 'z3_solve_time': solve_time,
        'z3_total_time': build_time + solve_time,
        'result': str(result),
    }


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    r = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    if len(sys.argv) > 1:
        print(run(n_routers=n, distractors_per_router=r))
    else:
        for rr in (10, 50, 100, 200, 400):
            row = run(n_routers=5, distractors_per_router=rr)
            print("n_routers=5 distractors_per_router=%-4d -> result=%s "
                  "build=%.4fs solve=%.4fs total=%.4fs"
                  % (rr, row['result'], row['z3_build_time'],
                    row['z3_solve_time'], row['z3_total_time']))
