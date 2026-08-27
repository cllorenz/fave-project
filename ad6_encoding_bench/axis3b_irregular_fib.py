"""Axis 3 follow-up (AD6_ENCODING_PLAN.md §3.2's caveat): does the
quantifier/array-theory structural win from axis3_array_uf.py survive on
an IRREGULAR rule set -- no clean contiguous index range to exploit -- the
actual shape of §5.2's open question (Stanford/i2's real FIB/VLAN
structure), instead of axis3's best-case linear-index range?

Same logical shape as axis3 (R independent "block this /L prefix"
distractors + the real destination -> ACCEPT), but each distractor now
has an INDEPENDENT, deterministically-pseudo-random address and prefix
length (16..56, no arithmetic relationship to its index i) -- nothing for
a quantifier's decision procedure to collapse algebraically, unlike
axis3's `hextet == i` structure.

Three encodings:
1. ad6's real pipeline (capped at a modest R -- already confirmed severely
   superlinear by axis3_array_uf.py; not the point of re-confirming here).
2. Z3 QF_BV, GROUND -- R separate ground Extract-range exclusions, one per
   rule's own (address, length) -- no shared structure to exploit, same as
   axis3's "ground" baseline.
3. Z3 QUANTIFIED-VIA-ARRAY-TABLE -- the honest way to phrase "R stored,
   irregular table entries" as a single quantified formula: two Arrays
   (addr_table, len_table : BitVec(16) -> BitVec(128)/BitVec(8)) populated
   via R Store operations (building the array is still O(R) -- there is no
   way around specifying R independent rules, same as ad6 above), then ONE
   z3.ForAll over the index variable referencing the arrays, instead of R
   ground literal instances. This is the fair test of whether array/UF
   theory's *general* mechanism still helps once there's no algebraic
   pattern in the data for it to notice, not just whether one specific
   contiguous-range example happens to reduce to Presburger arithmetic.

Usage: PYTHONPATH=../ad6 python3 axis3b_irregular_fib.py
"""
import sys
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

import z3

from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser
from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter

FW_NAME = 'axis3b'
DEST_PREFIX_LEN = 64
DEST_VALUE = 0x2001_0db8_beef_0000_0000_0000_0000_0000  # 2001:db8:beef::/64


def irregular_prefixes(r_distractors, seed=42):
    """Deterministic pseudo-random (address, prefix_len) pairs, prefix_len
    in [16,56], address drawn independently per entry -- no arithmetic
    relationship to the index, and no overlap with DEST_VALUE's own /64
    (checked, not just assumed) so the real destination always remains
    reachable regardless of R."""
    rng = random.Random(seed)
    prefixes = []
    while len(prefixes) < r_distractors:
        length = rng.choice([16, 20, 24, 28, 32, 40, 48, 56])
        value = rng.getrandbits(128) & (((1 << length) - 1) << (128 - length))
        if (value >> (128 - min(length, DEST_PREFIX_LEN))) == \
           (DEST_VALUE >> (128 - min(length, DEST_PREFIX_LEN))):
            continue  # would shadow/overlap the real destination -- redraw
        prefixes.append((value, length))
    return prefixes


def _value_to_v6(value, length):
    groups = [(value >> (112 - 16 * i)) & 0xffff for i in range(8)]
    return ':'.join('%x' % g for g in groups) + '/%d' % length


def build_ad6_ruleset(prefixes):
    lines = ['ip6tables -P ROUTER1 DROP']
    for value, length in prefixes:
        lines.append('ip6tables -A ROUTER1 -d %s -j DROP' % _value_to_v6(value, length))
    lines.append('ip6tables -A ROUTER1 -d 2001:db8:beef::/64 -j ACCEPT')
    return '\n'.join(lines) + '\n'


def run_ad6(prefixes):
    ruleset = build_ad6_ruleset(prefixes)
    fw = IP6TablesParser.parse(ruleset, FW_NAME)
    config = GenUtils.config()
    firewalls = GenUtils.firewalls()
    firewalls.append(fw)
    config.append(firewalls)

    t0 = time.perf_counter()
    kripke, encoding = Instantiator.InstantiateBase(
        config, Inits=['%s_router1_r0' % FW_NAME], default_inits=False)
    t1 = time.perf_counter()
    instance = Instantiator.InstantiateReach(kripke, encoding, '%s_accept_r0' % FW_NAME)
    solver = PycoSATAdapter()
    result = solver.Solve(instance)
    t2 = time.perf_counter()
    return {'build': t1 - t0, 'solve': t2 - t1, 'total': t2 - t0, 'result': bool(result)}


def run_z3_ground(prefixes):
    dst = z3.BitVec('dst', 128)

    t0 = time.perf_counter()
    not_any = z3.And(*[
        z3.Extract(127, 128 - length, dst) != z3.BitVecVal(value >> (128 - length), length)
        for value, length in prefixes
    ]) if prefixes else z3.BoolVal(True)
    dest_matches = z3.Extract(127, 64, dst) == z3.BitVecVal(DEST_VALUE >> 64, 64)
    solver = z3.Solver()
    solver.add(not_any, dest_matches)
    build_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = solver.check()
    solve_time = time.perf_counter() - t1
    return {'build': build_time, 'solve': solve_time,
            'total': build_time + solve_time, 'result': str(result)}


def run_z3_quantified_array(prefixes, timeout_ms=20000):
    r = len(prefixes)
    dst = z3.BitVec('dst', 128)
    i = z3.BitVec('i', 32)

    t0 = time.perf_counter()
    addr_table = z3.Array('addr_table', z3.BitVecSort(32), z3.BitVecSort(128))
    len_table = z3.Array('len_table', z3.BitVecSort(32), z3.BitVecSort(8))
    for idx, (value, length) in enumerate(prefixes):
        addr_table = z3.Store(addr_table, z3.BitVecVal(idx, 32), z3.BitVecVal(value, 128))
        len_table = z3.Store(len_table, z3.BitVecVal(idx, 32), z3.BitVecVal(length, 8))

    stored_addr = z3.Select(addr_table, i)
    stored_len = z3.Select(len_table, i)
    # for a given i, "dst matches table entry i" -- masking dst to
    # stored_len bits via a variable-width shift (Z3 supports symbolic
    # shift amounts on bitvectors, this is the genuinely "irregular"
    # bit: unlike axis3's fixed hextet slice, the mask width itself is
    # data, not syntax).
    mask = ~(z3.LShR(z3.BitVecVal(-1, 128), z3.ZeroExt(120, stored_len)))
    matches_i = z3.And(
        z3.ULT(i, z3.BitVecVal(r, 32)),
        (dst & mask) == (stored_addr & mask),
    )
    not_any = z3.ForAll([i], z3.Not(matches_i))
    dest_matches = z3.Extract(127, 64, dst) == z3.BitVecVal(DEST_VALUE >> 64, 64)

    solver = z3.Solver()
    solver.set('timeout', timeout_ms)
    solver.add(not_any, dest_matches)
    build_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = solver.check()
    solve_time = time.perf_counter() - t1
    return {'build': build_time, 'solve': solve_time,
            'total': build_time + solve_time, 'result': str(result)}


if __name__ == '__main__':
    sizes = [10, 100, 500, 1000, 5000]

    print(f"{'R':>7} {'ad6_total':>10} {'z3_ground':>10} {'z3_quant_array':>15}")
    for r in sizes:
        prefixes = irregular_prefixes(r)
        ad6_row = run_ad6(prefixes) if r <= 500 else None
        ground_row = run_z3_ground(prefixes)
        quant_row = run_z3_quantified_array(prefixes)

        print(f"{r:>7} "
              f"{('%.4fs' % ad6_row['total']) if ad6_row else 'skipped':>10} "
              f"{ground_row['total']:>10.4f} "
              f"{quant_row['total']:>15.4f}  "
              f"[{ad6_row['result'] if ad6_row else '-'}/{ground_row['result']}/"
              f"{quant_row['result']}]")
