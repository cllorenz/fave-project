#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

""" Subprocess bridge driven by fave/ad6/adapter.py (AD6_PLAN.md §4.2/§4.4).

Reads a JSON payload {"ir": <Ad6Adapter._build_ir() output>, "queries": [...]},
builds the ad6 Kripke/SAT model via src.parser.favemodel, answers every query
(source->probe existential reachability, src-IP seeded when the source has one),
and writes back [{"source","probe","reachable","negated","cond"}, ...].

Usage: python3 fave_bridge.py --in payload.json --out results.json
(run with cwd=ad6/, exactly like main.py -- see fave/ad6/adapter.py).
"""

import argparse
import json
import os
import sys
import time

sys.setrecursionlimit(10 ** 6)

import lxml.etree as et  # noqa: E402  (after recursionlimit, matches main.py's ordering)

from src.bigstack import run_with_big_stack  # noqa: E402
from src.core.instantiator import Instantiator  # noqa: E402
from src.parser import favemodel  # noqa: E402
from src.solver.pycosat import PycoSATAdapter  # noqa: E402
from src.xml.xmlutils import XMLUtils  # noqa: E402


def _seed_literals(cidr):
    """ The individual (already-canonical) src-IP bit literals to force onto
    a query instance so the packet's source is constrained to lie in `cidr`.
    Version is sniffed from the CIDR text (wl_ifi's generators are IPv4;
    wl_up's are IPv6 -- AD6_PLAN.md §5.1).

    MUST use XMLUtils.ConvertCIDRToVariables directly (a flat conjunction of
    "ip<version>_src_<i>=<bit>" literals in the shared bit-vector space every
    rule's own address condition is built over), FLATTENED and appended
    individually as top-level clauses -- exactly the same discipline
    `_state_literals` below already follows for state, and for the same
    reason: a bare named-alias variable (XMLUtils.ConvertToVariables's
    <ip>-element form, what this used to build) only carries meaning if that
    EXACT alias name happens to already be `Handled` (defined via an
    equality clause during Instantiator.InstantiateBase's scan) by some
    OTHER rule in the model referencing that exact address/CIDR string.
    wl_up's real bug this caused (AD6_PLAN.md §5.1 "bug 2"): each of 8
    structurally identical singleton-host source addresses is only ever
    matched via a broader containing /64 in the real rulesets, never
    verbatim itself -- so the alias was a free, unconnected atom for 7 of
    the 8 (only the one whose exact address happened, by coincidence, to
    also be referenced elsewhere in the corpus was actually constrained),
    silently bypassing an explicit source-scoped DROP rule for the other 7.
    Regression: ad6/test/core/instantiatortest.py:
    testSrcCidrQuerySeedMustUseSharedBitVector. """
    version = '6' if ':' in cidr else '4'
    elem = et.fromstring(
        '<ip xmlns="http://config" version="%s" direction="src">'
        '<address>%s</address></ip>' % (version, cidr)
    )
    XMLUtils.deannotate(elem)
    canonical = XMLUtils.CanonizeIP(elem)
    return list(XMLUtils.ConvertCIDRToVariables(canonical, 'src'))


# AD6_PLAN.md §4.2/§1.2/§1.4: FaVe's compliance-check semantics carry the
# stateful `<->>` query's third dimension as a `RuleField`-shaped condition
# in `cond` -- {"name": "related", "value": "0"|"1", ...} once it has
# travelled through the aggregator's real dispatch (RuleField.from_json,
# then Ad6Adapter._cond_to_json's JSON-safe echo of RuleField.to_json()).
# "0"=NEW / "1"=ESTABLISHED, matching fave/ad6/adapter.py:_RELATED and
# fave/iptables/generator.py's state-shell, which only ever emits these two
# values -- never a compound state. ad6 already carries the matching <state>
# vocabulary end to end (favemodel.py emits it on the ACL rule whose ctstate
# condition FaVe's model recorded); what's missing was the
# query-orchestration to force it here.
_RELATED_STATE = {"0": "NEW", "1": "ESTABLISHED"}


def _state_literals(cond):
    """ The individual (already-canonical) state-bit literals to force onto
    a query instance for a `{"name": "related", "value": "0"|"1"}` entry in
    `cond`, or [] if `cond` carries no state condition.

    MUST use XMLUtils.ConvertStateToVariables(value) directly (a flat
    conjunction of "state_<i>=<bit>" literals for the canonical STATES
    bit-vector) rather than a raw <state>value</state> element run through
    ConvertToVariables -- the latter produces ONE variable literally named
    "state_<value>", which only gets canonicalised into the shared bit-vector
    space by Instantiator._HandleOthers's build-time pass over the BASE
    model's own variables; a value that never appears in any rule (e.g.
    "NEW", when every ACL rule here only ever matches ctstate ESTABLISHED)
    would stay an unconnected, unconstrained atom and silently fail to
    conflict with an ESTABLISHED-only permit path. Calling
    ConvertStateToVariables ourselves reuses the exact same canonical
    "state_<i>=<bit>" names ad6 already assigns to ESTABLISHED via that same
    function, so forcing NEW here correctly conflicts with an
    ESTABLISHED-only branch regardless of whether "NEW" is otherwise used
    anywhere in the model. (Verified empirically before relying on it --
    appending the WHOLE <conjunction> XMLUtils.ConvertStateToVariables
    returns as one nested child of instance[0] does NOT work, because
    instance[0] is the already-CNF'd clause list from InstantiateBase: each
    top-level child must be its own flat literal/clause, so this flattens
    the conjunction's children before appending. See
    ad6/FAVE_CHANGES.md and AD6_PLAN.md §4.2 for the fixture that pinned
    this down.) """
    literals = []
    for c in (cond or []):
        if not isinstance(c, dict) or c.get("name") != "related":
            continue
        state = _RELATED_STATE.get(str(c.get("value")))
        if state is not None:
            literals.extend(list(XMLUtils.ConvertStateToVariables(state)))
    return literals


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='infile', required=True)
    parser.add_argument('--out', dest='outfile', required=True)
    args = parser.parse_args(argv)

    with open(args.infile) as raw:
        payload = json.load(raw)
    ir = payload['ir']
    queries = payload['queries']

    config = favemodel.build_config(ir)
    XMLUtils.deannotate(config)
    kripke, encoding = favemodel.instantiate_base(config, ir)
    # Mutual exclusion between generators (at most one of favemodel.init_keys()
    # fires per query) is enforced by KripkeUtils._CreateInitConstraints on
    # the base model itself -- no per-query exclusivity assertion needed here
    # (there used to be one; removed once the ad6-core off-by-one it was
    # working around was fixed and verified sufficient on its own, see
    # ad6/FAVE_CHANGES.md §8).

    solver = PycoSATAdapter()
    # AD6_PLAN.md §5.4 Stage B (B1), Option 2: shared across every query in
    # this run -- Instantiator.SolveAcyclicEndToEnd lazily builds the
    # (expensive) SCC-scoped acyclic rank constraints into this dict the
    # FIRST time any query's witness turns out ungrounded, then reuses them
    # for every subsequent query, rather than rebuilding per query.
    acyclic_cache = {}
    results = []
    # Opt-in per-query progress (AD6_BRIDGE_PROGRESS=1) -- added after the
    # B1 Option 2 differential ran for hours with zero visibility into
    # which query it was on or whether it had hit the (expensive)
    # escalation path yet. Off by default so it never clutters normal
    # subprocess output/logs.
    #
    # fave/ad6/adapter.py's Ad6Adapter.check_compliance -- the ONLY real
    # caller -- invokes this whole script as one subprocess.run(...,
    # stderr=subprocess.PIPE) call: the pipe is fully buffered in the OS
    # and only handed back to the parent once THIS PROCESS EXITS, so
    # anything written to stderr is invisible until the entire (possibly
    # hours-long) run is already over -- useless for watching a live run.
    # AD6_BRIDGE_PROGRESS_FILE=<path> writes line-buffered progress to a
    # real file instead, independent of the parent's own stdout/stderr
    # capture, so `tail -f` on that path works regardless of how (or
    # whether) a caller captures this process's own streams.
    progress = bool(os.environ.get('AD6_BRIDGE_PROGRESS'))
    progress_file = os.environ.get('AD6_BRIDGE_PROGRESS_FILE')
    progress_out = sys.stderr
    if progress and progress_file:
        progress_out = open(progress_file, 'a', buffering=1)
    total = len(queries)
    for index, q in enumerate(queries, start=1):
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.query_destination_key(q['probe'], ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, destination)
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            instance[0].extend(_seed_literals(q['src_cidr']))
        for literal in _state_literals(q.get('cond')):
            instance[0].append(literal)
        # AD6_PLAN.md §5.4 Stage B (B1): InstantiateEndToEnd's own two
        # independent disjuncts are unsound on cyclic topologies (see
        # instantiatortest.py::testCycleReachabilityIsUnsoundWithoutRealOrigin).
        # SolveAcyclicEndToEnd rejects any witness not actually grounded in
        # `source`, escalating to the static rank fix only when a plain
        # solve's witness needs it. Applied here, at the one call site
        # every query goes through, so it can't be forgotten by a future
        # caller.
        stats = {} if progress else None
        if progress:
            start = time.time()
        reachable = Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, source, destination, Cache=acyclic_cache, Stats=stats)
        if progress:
            tag = "escalated" if stats['Escalated'] else "fast-path"
            print("[%d/%d] %s -> %s: reachable=%s (%s, %.2fs)" % (
                index, total, q['source'], q['probe'], reachable, tag,
                time.time() - start), file=progress_out, flush=True)
        results.append({
            "source": q['source'], "probe": q['probe'],
            "reachable": reachable, "negated": q['negated'], "cond": q['cond'],
        })

    if progress and progress_file:
        progress_out.close()

    with open(args.outfile, 'w') as raw:
        json.dump(results, raw)
    return 0


if __name__ == '__main__':
    # AD6_PLAN.md §5.4 Stage B, B1's "third item" / AD6_ENCODING_PLAN.md
    # §3.10: sys.setrecursionlimit(10**6) above lets deep recursive
    # operations on a real cyclic topology's escalated (rank-constrained)
    # instance run past the OS's actual C stack (bounded by ulimit -s,
    # independent of the Python-level counter) and segfault SILENTLY --
    # confirmed on the real wl_stanford model under the shell's default
    # 8MB stack. run_with_big_stack runs main() in a thread with an
    # explicit large stack instead, so this can't happen regardless of
    # what ulimit the parent process (Ad6Adapter.check_compliance's
    # subprocess.run) happens to inherit.
    sys.exit(run_with_big_stack(main))
