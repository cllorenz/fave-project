"""Axis 3 (AD6_ENCODING_PLAN.md §3/§4): does an array/UF-theory-style FIB
model give a STRUCTURAL win (not just a mature-tooling one) over Axis 2's
plain QF_BV encoding?

Design note (why this isn't "more nested nesting" -- worth reading before
touching the numbers): a genuine LPM tie-break (narrower overrides wider)
does NOT actually stress an *existential* reachability query -- a solver
free to pick ANY satisfying witness address will just pick one matching
the simplest/widest relevant rule, sidestepping the tie-break entirely.
Nesting only bites a query that fixes the address externally or asks
"for all addresses" -- neither of which is ad6/FaVe's actual query shape
(point existential reachability, AD6_PLAN.md §1.2's own primitive table).
So the honest structural-win candidate isn't overlap/nesting -- it's
whether a PARAMETRIC family of R otherwise-independent (Axis-2-style,
mutually disjoint) rules can be represented as ONE constraint over an
index variable instead of R ground instances, the way a real routing
table's contiguous range naturally could be, and the way a domain-specific
tool's "one flood answers all" (AD6_PLAN.md's Factor A) already exploits
structure ad6 can't.

Three encodings of the SAME R rules (a router with R "block this specific
/64 sub-range" distractors, indexed 0..R-1, plus a genuine forward/accept
path), same logical content each time:

1. ad6's real pipeline -- R separate ip6tables rules (this is how any real
   ruleset/FIB actually has to be specified rule-by-rule; there's no
   "collapse the range" option available to it. Not a fair vs. unfair
   comparison, just the honest baseline for "this is the cost of the rules
   as literally written").
2. Z3 QF_BV, GROUND -- R separate ground Extract==BitVecVal(i) exclusions,
   mirroring axis2_smt.py's style exactly (no algebraic insight used).
3. Z3 QF_BV, COLLAPSED -- because these R distractors are laid out as a
   contiguous index range by construction, "excluded by some distractor"
   collapses ALGEBRAICALLY to one inequality (hextet < R). This is what a
   structure-aware model (or a genuinely successful quantifier
   elimination) would give -- the plan's "structural, not just
   engineering-maturity" win candidate, made concrete.
4. Z3 QF_BV, QUANTIFIED -- an actual z3.ForAll over the index variable,
   asking Z3's OWN quantifier instantiation to find (1) or (3)'s behavior
   on its own, rather than hand-deriving the collapse. This is the fair
   test of "would array/UF/quantified theory let the SOLVER avoid
   enumerating R terms," not just "can a human avoid it."

Usage: PYTHONPATH=../ad6 python3 axis3_array_uf.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

import z3

from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser
from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter

FW_NAME = 'axis3'
DEST_PREFIX = '2001:db8:beef::/64'


def build_ad6_ruleset(r_distractors):
    """One router: R fixed-/64 distractors (2001:db8:d000:0::/64 ..
    2001:db8:d000:{R-1}::/64), then the real destination -> ACCEPT."""
    lines = ['ip6tables -P ROUTER1 DROP']
    for i in range(r_distractors):
        lines.append('ip6tables -A ROUTER1 -d 2001:db8:d000:%x::/64 -j DROP' % i)
    lines.append('ip6tables -A ROUTER1 -d %s -j ACCEPT' % DEST_PREFIX)
    return '\n'.join(lines) + '\n'


def run_ad6(r_distractors):
    ruleset = build_ad6_ruleset(r_distractors)
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


def run_z3_ground(r_distractors):
    dst = z3.BitVec('dst', 128)
    hextet2 = z3.Extract(79, 64, dst)   # third hextet: the "d000" block marker
    hextet3 = z3.Extract(63, 48, dst)   # fourth hextet: the varying index i

    t0 = time.perf_counter()
    not_any_distractor = z3.And(*[
        z3.Or(hextet2 != z3.BitVecVal(0xd000, 16), hextet3 != z3.BitVecVal(i, 16))
        for i in range(r_distractors)
    ]) if r_distractors else z3.BoolVal(True)
    dest_matches = z3.Extract(127, 64, dst) == z3.BitVecVal(0x2001_0db8_beef_0000, 64)
    solver = z3.Solver()
    solver.add(not_any_distractor, dest_matches)
    build_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = solver.check()
    solve_time = time.perf_counter() - t1
    return {'build': build_time, 'solve': solve_time,
            'total': build_time + solve_time, 'result': str(result)}


def run_z3_collapsed(r_distractors):
    dst = z3.BitVec('dst', 128)
    hextet2 = z3.Extract(79, 64, dst)
    hextet3 = z3.Extract(63, 48, dst)

    t0 = time.perf_counter()
    # "excluded by some distractor(i), i in [0,R)" collapses to one range
    # check because the R distractors are a contiguous index range by
    # construction -- the algebraic insight a structure-aware model needs.
    not_any_distractor = z3.Or(
        hextet2 != z3.BitVecVal(0xd000, 16),
        z3.UGE(hextet3, z3.BitVecVal(r_distractors, 16)),
    )
    dest_matches = z3.Extract(127, 64, dst) == z3.BitVecVal(0x2001_0db8_beef_0000, 64)
    solver = z3.Solver()
    solver.add(not_any_distractor, dest_matches)
    build_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = solver.check()
    solve_time = time.perf_counter() - t1
    return {'build': build_time, 'solve': solve_time,
            'total': build_time + solve_time, 'result': str(result)}


def run_z3_quantified(r_distractors, timeout_ms=15000):
    dst = z3.BitVec('dst', 128)
    hextet2 = z3.Extract(79, 64, dst)
    hextet3 = z3.Extract(63, 48, dst)
    i = z3.BitVec('i', 16)

    t0 = time.perf_counter()
    # ask Z3's OWN quantifier instantiation to derive the exclusion,
    # instead of hand-deriving it (run_z3_collapsed) or grounding it
    # (run_z3_ground).
    not_any_distractor = z3.ForAll(
        [i],
        z3.Implies(
            z3.ULT(i, z3.BitVecVal(r_distractors, 16)),
            z3.Or(hextet2 != z3.BitVecVal(0xd000, 16), hextet3 != i),
        ),
    )
    dest_matches = z3.Extract(127, 64, dst) == z3.BitVecVal(0x2001_0db8_beef_0000, 64)
    solver = z3.Solver()
    solver.set('timeout', timeout_ms)
    solver.add(not_any_distractor, dest_matches)
    build_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = solver.check()
    solve_time = time.perf_counter() - t1
    return {'build': build_time, 'solve': solve_time,
            'total': build_time + solve_time, 'result': str(result)}


if __name__ == '__main__':
    sizes = [10, 100, 1000, 5000, 20000]

    print(f"{'R':>7} {'ad6_total':>10} {'z3_ground':>10} "
          f"{'z3_collapsed':>13} {'z3_quantified':>14}")
    for r in sizes:
        ad6_row = run_ad6(r) if r <= 5000 else None  # ad6's own pipeline gets slow; cap it
        ground_row = run_z3_ground(r)
        collapsed_row = run_z3_collapsed(r)
        quant_row = run_z3_quantified(r)

        print(f"{r:>7} "
              f"{('%.4fs' % ad6_row['total']) if ad6_row else 'skipped':>10} "
              f"{ground_row['total']:>10.4f} "
              f"{collapsed_row['total']:>13.4f} "
              f"{quant_row['total']:>14.4f}  "
              f"[{ad6_row['result'] if ad6_row else '-'}/{ground_row['result']}/"
              f"{collapsed_row['result']}/{quant_row['result']}]")
