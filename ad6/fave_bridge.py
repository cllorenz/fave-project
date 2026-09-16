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

Reads a JSON payload {"literal": <Ad6Adapter._build_literal() output>,
"queries": [...]}, builds the ad6 Kripke/SAT model from the config XML the
translator already produced, answers every query (source->probe existential
reachability, src-IP seeded when the source has one), and writes back
[{"source","probe","reachable","negated","cond"}, ...].

AD6_PLAN.md §9.25: this used to have a SECOND path, building the model HERE
from an IR of interpreted concepts via `src.parser.favemodel`. Both that path
and `favemodel.py` are gone; the model now arrives already translated, so this
script's whole job is to instantiate it and run the query loop.

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
from src.solver.incremental import (  # noqa: E402
    GROUNDING_RANK, GROUNDINGS, SOLVER_MINISAT22, SOLVERS, IncrementalSession)
from src.xml.xmlutils import XMLUtils  # noqa: E402
from src.core.kripke import KripkeUtils  # noqa: E402
from src.core.instantiator import Instantiator  # noqa: E402
from src.sat.satutils import SATUtils  # noqa: E402


def _seed_literals(cidr):
    """ The individual (already-canonical) src-IP bit literals to force onto
    a query instance so the packet's source is constrained to lie in `cidr`.
    Version is sniffed from the CIDR text (wl_ifi's generators are IPv4;
    wl_up's are IPv6 -- AD6_PLAN.md §5.1).

    MUST use XMLUtils.ConvertCIDRToVariables directly (a flat conjunction of
    "ip<version>_src_<i>=<bit>" literals in the shared bit-vector space every
    rule's own address condition is built over), FLATTENED and appended
    individually as top-level clauses -- the same discipline
    `_state_field_literals` below follows for state, and for the same
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
# values -- never a compound state. A STRUCTURAL model carries `related` as an
# ordinary header field rather than as ad6's own <state> vocabulary (§9.2a:
# FaVe's interweaving strips conntrack and re-emits a plain field), so this
# mapping no longer forces anything -- it survives to NAME the two values a
# `related` condition may carry. The <state>-forcing counterpart went with the
# semantic path at §9.25.
_RELATED_STATE = {"0": "NEW", "1": "ESTABLISHED"}

# The only query-condition field that can be forced onto an instance. A
# check conditioned on anything else (wl_example emits `protocol`/`port`)
# cannot be honoured at all -- see _validated_conditions.
_SUPPORTED_COND_FIELDS = ("related",)


def _validated_conditions(cond, path):
    """ The `related` entries of `cond`, REFUSING anything this bridge cannot
    force onto the query instance (AD6_PLAN.md §9.23.2a).

    Both query paths used to `continue` past whatever they did not recognise.
    That is the most expensive shape of bug this codebase has produced: a
    dropped condition does not fail, it answers the UNCONDITIONED question and
    returns a confident number. §9.23 is a full post-mortem of one such number
    -- a published finding about `related` "not discriminating" that was
    entirely an artifact of conditions passed in the wrong shape and silently
    discarded.

    So nothing is skipped. Either a condition is honoured or the caller hears
    about it. """
    for condition in (cond or []):
        if not isinstance(condition, dict):
            raise ValueError(
                "malformed query condition %r on the %s path: expected a "
                "RuleField.to_json() dict like {'name': 'related', 'value': "
                "'0'}, got %s. Skipping it would answer the UNCONDITIONED "
                "question -- AD6_PLAN.md §9.23.2a."
                % (condition, path, type(condition).__name__))

        name = condition.get("name")
        if name is None:
            raise ValueError(
                "malformed query condition %r on the %s path: no 'name' field "
                "(AD6_PLAN.md §9.23.2a)." % (condition, path))

        if name not in _SUPPORTED_COND_FIELDS:
            raise ValueError(
                "query condition %r cannot be honoured: the %s query path "
                "forces only %s, not %r. It is NOT dropped, because answering "
                "the unconditioned question looks like a result "
                "(AD6_PLAN.md §9.23.2a)."
                % (condition, path, "/".join(_SUPPORTED_COND_FIELDS), name))

        yield condition


# MOVED HERE at AD6_PLAN.md §9.25 from `src/parser/favemodel.py`, which is
# deleted. This pair was the one thing the surviving query path still took
# from that module, so it is copied VERBATIM rather than re-derived -- a
# paraphrase like `not cidr.endswith("/0")` is not the same predicate (it
# would call an unlisted "10.0.0.0/0" unconstrained), and this decides whether
# a query gets seeded at all.
_MATCH_ALL = frozenset({"0.0.0.0/0", "::/0", "0::0/0", None})


def _is_constrained(cidr):
    """ False for a match-all address (None, or the literal "0.0.0.0/0" FaVe
    emits for an explicit "any" ACL match). A match-all condition is exactly
    "no condition", so a query carrying one is left unseeded rather than
    asserting it -- semantically identical either way, and one fewer variable
    in the encoding.

    This used to be load-bearing, not just a simplification:
    XMLUtils.ConvertCIDRToVariables truncated a /0 prefix's bit-vector to
    zero bits (Count*2 == 0), producing a Kripke node whose Gamma was an
    EMPTY <conjunction/> instead of a trivially-true condition -- and
    Instantiator._ShortenPrefixes treats a /0 entry as a (trivial) prefix of
    every other same-direction CIDR, splicing a reference to it into their
    conjunctions too, so the corruption spread to rules that never mentioned
    0.0.0.0/0 at all. Fixed in ad6 core 2026-08-21 -- ConvertCIDRToVariables
    now returns XMLUtils.constant() for a /0 prefix; see ad6/FAVE_CHANGES.md
    §7 and ad6/test/core/instantiatortest.py:testMatchAllReachable for the
    regression test. Kept anyway: omitting a redundant condition is good
    hygiene independent of whether the underlying bug is fixed. """
    return cidr not in _MATCH_ALL


def _state_field_literals(cond, field_widths, node):
    """ AD6_PLAN.md §9.19: force a `related:N` query condition onto the
    model's own `related` FIELD (hence the name -- §9.26).

    The model carries `related` as an ordinary field, matched with a
    node-scoped <fieldmatch> (§9.2a: FaVe's interweaving strips conntrack and
    re-emits `related` as a plain header field), so the bits are forced onto
    that field. The semantic path's deleted counterpart emitted ad6 `<state>`
    variables instead, which this model never uses -- feeding it those would
    have constrained NOTHING, and 3,302 of wl_up's 11,902 cchecks carry such a
    condition, so the `related:0` and `related:1` variants of one check would
    have come back with the SAME answer, silently.

    Forcing the bits at the QUERY's own source node is sufficient because
    nothing rewrites `related`: _CreateMutationConstraints frames it unchanged
    across every edge, so pinning one node on the path pins the whole path.

    Shape and field-name validation live in `_validated_conditions` --
    nothing is ever skipped (§9.23.2a). On top of that this refuses two cases
    of its own:

      * a non-integer `related` value;
      * a well-formed `related` condition against a model that
        declares no `related` field, so there is nothing to bind the bits to.
        Forcing nothing here would silently answer the UNCONDITIONED question,
        which is the exact failure §9.23 is a post-mortem of.

    Pinned by fave/test/test_ad6_bridge_cond.py. """
    literals = []
    for condition in _validated_conditions(cond, "literal"):
        width = (field_widths or {}).get('related')
        if width is None:
            raise ValueError(
                "query condition %r cannot be honoured: this model "
                "declares no 'related' field, so nothing can be forced and the "
                "query would silently answer the UNCONDITIONED question "
                "(AD6_PLAN.md §9.23.2a). Declared fields: %s."
                % (condition, sorted(field_widths or {})))

        raw = condition.get("value")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(
                "malformed query condition %r: 'related' value %r is not an "
                "integer (AD6_PLAN.md §9.23.2a)." % (condition, raw)) from None

        bits = XMLUtils._CanonizeBitvector(value, width).split(' ')
        for index, bit in enumerate(bits):
            literals.append(XMLUtils.variable(
                XMLUtils.FieldBitName('related', node, index), bit == '1'))
    return literals


def _instantiate_literal(config, edges, inits, mutable_fields=None):
    """ Instantiator.InstantiateBase's body with the translator's own edges
    spliced in between ConvertToKripke and the base-implication build.

    The splice is unavoidable rather than a shortcut: the edges reference
    interface NODES, which do not exist until conversion has run, and there is
    no public seam between the two halves. Mirrors fave/ad6/translate.py's own
    instantiate_base (which is what the translator's unit tests drive); keep the
    two, and src/core/instantiator.py:InstantiateBase, in step.

    The variable-expansion pass at the end is NOT optional: without it a CIDR
    stays one opaque alias variable and two prefixes are independent booleans,
    so nothing makes 10.0.0.0/8 and 192.168.0.0/16 mutually exclusive and every
    disjoint path comes back spuriously reachable. """
    kripke = KripkeUtils.ConvertToKripke(config, default_inits=False)

    for init in inits:
        node = kripke.GetNode(init)
        if XMLUtils.INIT not in node.Props:
            node.Props.append(XMLUtils.INIT)
        kripke.PutInit(init, node)

    for source, target in edges:
        kripke.Put(source, (target, True))

    encoding = Instantiator._InstantiateBase(kripke)

    if mutable_fields:
        encoding[0].extend(
            Instantiator._CreateMutationConstraints(kripke, mutable_fields))

    handled = {}
    for variable in encoding.iterdescendants(XMLUtils.VARIABLE):
        Instantiator._HandlePrefixes(variable, handled)
        Instantiator._HandlePorts(variable, handled)
        Instantiator._HandleVlans(variable, handled)
        Instantiator._HandleFieldMatches(variable, handled, mutable_fields)
        Instantiator._HandleOthers(variable, handled)

    keys = list(handled)
    Instantiator._ShortenPrefixes(handled, [k for k in keys if k.startswith('src_')])
    Instantiator._ShortenPrefixes(handled, [k for k in keys if k.startswith('dst_')])

    encoding[0].extend(list(handled.values()))
    encoding[0].extend(Instantiator._CreateGlobalConstraints(kripke, encoding))
    SATUtils.ConvertToCNF(encoding)

    return kripke, encoding


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='infile', required=True)
    parser.add_argument('--out', dest='outfile', required=True)
    # AD6_PLAN.md §5.4 B1 / §5.5: which grounding constraint closes the
    # SECRYPT'15 gap for this run (src/solver/incremental.py's GROUNDINGS).
    # Normally set by the caller through the payload -- Ad6Adapter's own
    # `grounding` argument -- so this flag exists for driving the bridge by
    # hand; when both are given the flag wins.
    parser.add_argument('--grounding', choices=GROUNDINGS, default=None)
    # AD6_PLAN.md §9.3 Phase 6: same arrangement as --grounding. Normally set by
    # the caller through the payload (Ad6Adapter's own arguments); these exist
    # for driving the bridge by hand, and when both are given the flag wins.
    parser.add_argument('--solver', choices=SOLVERS, default=None)
    parser.add_argument('--lite-acyclic', dest='lite_acyclic',
                        action='store_true', default=None)
    args = parser.parse_args(argv)

    with open(args.infile) as raw:
        payload = json.load(raw)
    queries = payload['queries']

    # The model arrives ALREADY TRANSLATED -- fave/ad6/translate.py runs in
    # FaVe's process, because it needs BOTH vocabularies at once (ad6's GenUtils
    # to emit, FaVe's own rule_model to read) and only that side has FaVe. What
    # crosses the boundary is finished, namespace-free XML plus the Kripke edges
    # that XML cannot express (a FaVe link is unidirectional; a declarative
    # <connection keyref=...> would be wired BOTH ways and over-approximate).
    # So this script imports nothing from FaVe.
    literal = payload['literal']
    config = et.fromstring(literal['config'].encode('utf-8'))
    kripke, encoding = _instantiate_literal(
        config,
        edges=literal['edges'],
        inits=sorted(literal['sources'].values()),
        # Sent by the translator, which knows what it emitted.
        mutable_fields=literal.get('mutable_fields') or None)
    source_key = lambda q: literal['sources'][q['source']]
    destination_key = lambda q: literal['probes'][q['probe']]
    # Mutual exclusion between generators (at most one init key fires per
    # query) is enforced by KripkeUtils._CreateInitConstraints on
    # the base model itself -- no per-query exclusivity assertion needed here
    # (there used to be one; removed once the ad6-core off-by-one it was
    # working around was fixed and verified sufficient on its own, see
    # ad6/FAVE_CHANGES.md §8).

    # AD6_PLAN.md §6 / AD6_ENCODING_PLAN.md §§3.4-3.10: one persistent
    # incremental-solving session for the whole run, built once (base
    # encoding + SCC-scoped acyclic rank constraints, both baked in
    # unconditionally -- sound by construction, no CEGAR needed, see
    # src/solver/incremental.py's own docstring), then reused across
    # every query via native assumption-based solves. Replaces the old
    # per-query Instantiator.SolveAcyclicEndToEnd/PycoSATAdapter path
    # (kept intact in src/core/instantiator.py for its own direct
    # callers/tests -- only this call site changed): confirmed
    # ~100-490x faster on wl_up's real full query set and rescues
    # wl_stanford's B1 wall-clock NO-GO (~16 min for the real 256-pair
    # all-pairs matrix vs. an unfinished 6-hour run), 0 mismatches
    # against the old architecture on both.
    grounding = args.grounding or payload.get('grounding') or GROUNDING_RANK
    solver = args.solver or payload.get('solver') or SOLVER_MINISAT22
    lite_acyclic = (args.lite_acyclic if args.lite_acyclic is not None
                    else bool(payload.get('lite_acyclic')))
    session = IncrementalSession(kripke, encoding, grounding=grounding,
                                 solver=solver, lite_acyclic=lite_acyclic)
    # Always announce them, even without AD6_BRIDGE_PROGRESS: all three are
    # measurement-affecting configuration, so a run's own log must record what
    # produced its answers (AD6_PLAN.md's generality-debt gate). Read back off
    # the SESSION rather than echoed from the request -- `lite_acyclic` does not
    # apply under the flow grounding, and the log must say what was actually
    # used, not what was asked for.
    print("[ad6 bridge] grounding=%s solver=%s lite_acyclic=%s" % (
        session.grounding, session.solver, session.lite_acyclic),
        file=sys.stderr, flush=True)
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
        source = source_key(q)
        destination = destination_key(q)
        extra_vars = []
        if q.get('src_cidr') and _is_constrained(q['src_cidr']):
            extra_vars.extend(_seed_literals(q['src_cidr']))
        extra_vars.extend(_state_field_literals(
            q.get('cond'), literal.get('mutable_fields'), source))
        # NOTE (AD6_PLAN.md §5.5 C4 part 2, §9.9): there is deliberately no
        # probe-side VLAN forcing here. The semantic path had an opt-in
        # `probe_untag` that enforced a probe's declared arrival VLAN; a
        # probe accepts whatever the network delivers (owner
        # 2026-09-13), and a condition on a terminal rule would be silently
        # ignored anyway (§9.9.1) -- so forcing it would ask a different
        # question under the same name. Deleted with the rest of that path.
        if progress:
            start = time.time()
        reachable = session.Query(source, destination, extra_vars=extra_vars)
        if progress:
            print("[%d/%d] %s -> %s: reachable=%s (%.4fs)" % (
                index, total, q['source'], q['probe'], reachable,
                time.time() - start), file=progress_out, flush=True)
        results.append({
            "source": q['source'], "probe": q['probe'],
            "reachable": reachable, "negated": q['negated'], "cond": q['cond'],
        })
    session.Close()

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
