"""Minimal, isolated repro for a NEW correctness bug found while building the
H1/H2 microbenchmark harness's cyclic topology variant (see
../AD6_ENCODING_PLAN.md). Distinct from the already-known floating-cycle
soundness gap (AD6_PLAN.md Stage B / AD6_ENCODING_PLAN.md §2.4): this one is
an implementation bug in Instantiator._ConvertNodesToImplications, not a
theory-level gap in trans(C) itself -- the paper's own formula is correct
here; the code mistranslates it.

Root cause (src/core/instantiator.py, _ConvertNodesToImplications):

    if len(Transitions) > 1:
        Disjunction = XMLUtils.disjunction(); Disjunction.extend(Transitions)
    elif len(Transitions) == 1:
        Disjunction = Transitions[0]
    else:
        if XMLUtils.INIT in Node.Props:
            Disjunction = XMLUtils.constant()
        else:
            Disjunction = XMLUtils.constant(False)

This is meant to encode trans(C)'s "(trans(t,init) OR exists incoming
transition fired)" motivating disjunct (secrypt15.pdf §3.3) for the SOURCE
node `t` of an outgoing edge. But the "OR t is init" branch is reachable
ONLY when Transitions (t's OWN incoming edges) is empty. The MOMENT a node
has >=1 real incoming edge in the graph, the code drops "OR init" entirely
and requires ONE OF THOSE INCOMING EDGES TO ALSO FIRE -- even if the node
genuinely IS an init node. An init node that also happens to receive any
real incoming edge (a completely ordinary topology: e.g. a gateway/entry
router that is also on a real forwarding loop) loses its "trivially
motivated, no predecessor needed" property.

Effect: a query that is genuinely, structurally reachable from that init
node can come back spurious UNSAT, because the encoding wrongly demands an
unrelated predecessor edge also fire, and that predecessor edge's OWN guard
can conflict with the query's real answer (exactly what happens below).

This is a FALSE NEGATIVE (spurious UNSAT) bug, complementary to the
already-known FALSE POSITIVE (spurious SAT via floating cycles) gap -- the
two are opposite failure modes of "how does a node's reachability get
motivated," found via two different investigation paths, in two different
mechanisms (trans(C)'s own formula vs. its code translation).

Not fixed here -- this file only pins the mechanism down for whoever picks
it up. No ad6/ source files are touched.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser
from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter

# Router1 (init) forwards db8::/32 traffic to Router2. Router2 accepts the
# specific dest beef::/64 (a subset of db8::/32); anything else under
# db8::/32 loops back to Router1. beef::/64 traffic should plainly reach
# ACCEPT without ever touching the loop-back edge at all.
ruleset = """ip6tables -P ROUTER1 DROP
ip6tables -A ROUTER1 -d 2001:db8::/32 -j ROUTER2
ip6tables -P ROUTER2 DROP
ip6tables -A ROUTER2 -d 2001:db8:beef::/64 -j ACCEPT
ip6tables -A ROUTER2 -d 2001:db8::/32 -j ROUTER1
"""

fw = IP6TablesParser.parse(ruleset, 'bench')
config = GenUtils.config()
firewalls = GenUtils.firewalls()
firewalls.append(fw)
config.append(firewalls)

kripke, encoding = Instantiator.InstantiateBase(
    config, Inits=['bench_router1_r0'], default_inits=False)

solver = PycoSATAdapter()
instance = Instantiator.InstantiateReach(kripke, encoding, 'bench_accept_r0')
result = solver.Solve(instance)

print("ACCEPT reachable from init (expected True -- beef::/64 plainly "
      "flows Router1 -> Router2 -> ACCEPT, never touching the loop-back "
      "edge): got", bool(result))
assert bool(result) is False, (
    "if this now prints True, the bug may have been fixed -- update "
    "AD6_ENCODING_PLAN.md §2.5 and this docstring")
print("Bug reproduced: spurious UNSAT confirmed.")

print()
print("Isolating the mechanism: Router1's own outgoing edge should be "
      "trivially motivated (it IS the init node) with NO predecessor "
      "required at all.")
print("Router1_r0 backward transitions (should be irrelevant to its own "
      "init status, but the buggy code uses them anyway once non-empty):",
      list(kripke.IterBTransitions('bench_router1_r0')))
