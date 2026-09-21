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

THE CONDITION PATH IS RECIPE-DRIVEN (§9.37). It used to force exactly one
field, `related`, and refuse everything else. What replaced the allowlist is
`query_fields` in the payload: the translator says, per field, whether THIS
model resolved it to a node-scoped SSA copy or to the global bit-vector, since
that is a property of the model and forcing into the wrong namespace
constrains nothing at all. A field the map omits is one no rule matches or
rewrites, so a condition on it is honoured by forcing nothing -- announced on
stderr, because "honoured, there was nothing there" and "quietly dropped" must
not look alike.

Usage: python3 fave_bridge.py --in payload.json --out results.json
(run with cwd=ad6/, exactly like main.py -- see fave/ad6/adapter.py).
"""

import argparse
import ipaddress
import json
import os
import sys
import time

sys.setrecursionlimit(10 ** 6)

import lxml.etree as et  # noqa: E402  (after recursionlimit, matches main.py's ordering)

from copy import deepcopy  # noqa: E402

from src.bigstack import run_with_big_stack  # noqa: E402
from src.solver.incremental import (  # noqa: E402
    GROUNDING_RANK, GROUNDINGS, SOLVER_MINISAT22, SOLVERS, IncrementalSession)
from src.xml.xmlutils import XMLUtils  # noqa: E402
from src.core.kripke import KripkeUtils  # noqa: E402
from src.core.instantiator import Instantiator  # noqa: E402
from src.sat.satutils import SATUtils  # noqa: E402


def _seed_literals(cidr, recipes, field, node):
    """ The individual (already-canonical) src-IP bit literals to force onto
    a query instance so the packet's source is constrained to lie in `cidr`.
    Version is sniffed from the CIDR text (wl_ifi's generators are IPv4;
    wl_up's are IPv6 -- AD6_PLAN.md §5.1).

    MUST use XMLUtils.ConvertCIDRToVariables directly (a flat conjunction of
    "ip<version>_src_<i>=<bit>" literals in the shared bit-vector space every
    rule's own address condition is built over), FLATTENED and appended
    individually as top-level clauses -- the same discipline
    `_node_literals` below follows for a node-scoped field, and for the same
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
    testSrcCidrQuerySeedMustUseSharedBitVector.

    THE SHARED SPACE IS NOT ALWAYS THE GLOBAL ONE, which is what `recipes`
    is for. `ip<version>_src_<i>` is where a source address lives only while
    NOTHING REWRITES IT. A model with source NAT matches the field node-scoped
    instead (§9.6), and forcing the global vector there constrains nothing at
    all -- the same silent no-op this docstring is otherwise about, one level
    up. wl_cloud is such a model. So the namespace comes from the translator's
    own recipe, and the literals are forced at the SOURCE's node rather than
    the probe's: a generator's declared address is the header the packet
    STARTS with, which is a different statement from a check's condition on
    the header that ARRIVES.
    """
    recipe = (recipes or {}).get(field)
    if recipe is None:
        return []                       # no rule constrains the source address
    if recipe.get('scope') == 'node':
        return _node_literals(
            recipe, _cidr_to_ternary(cidr, recipe['width']), node,
            {'name': field, 'value': cidr})
    return _global_literals(recipe, cidr, {'name': field, 'value': cidr})


def _cidr_to_ternary(cidr, width):
    """ A CIDR as a ternary bit-vector of `width` bits: the prefix determined,
    the host part don't-care.

    A node-scoped address field is compared bit by bit, so a prefix needs no
    special case -- it is just a value whose low bits are free, exactly like a
    masked <fieldmatch>. wl_cloud's generators carry a `/30` each, which is why
    this is not the host-address-only shortcut it first looked like.
    """
    address, _, length = str(cidr).partition('/')
    if ':' in address:
        value, size = int(ipaddress.IPv6Address(address)), 128
    else:
        value = int.from_bytes(bytes(int(p) for p in address.split('.')), 'big')
        size = 32
    if size != width:
        raise ValueError(
            "address %r is %d bits but the model declares the field %d wide; "
            "ad6 compares a fixed-width vector, so the two cannot be the same "
            "field." % (cidr, size, width))
    prefix = int(length) if length else size
    return XMLUtils.TERNARY + format(value, '0%db' % size)[:prefix] + 'x' * (size - prefix)


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


#: FaVe's name for the source address, by IP version -- the key a
#: `query_fields` recipe for a generator's own address is filed under.
_SRC_ADDRESS_FIELD = {'4': 'packet.ipv4.source', '6': 'packet.ipv6.source'}


def _condition_recipe(condition, recipes, path):
    """ The forcing recipe for one query condition, or None when the model does
    not constrain the field at all (AD6_PLAN.md §9.23.2a).

    NOTHING IS EVER SILENTLY SKIPPED. That is the rule §9.23 is a post-mortem
    of: a dropped condition does not fail, it answers the UNCONDITIONED
    question and returns a confident number -- a published finding about
    `related` "not discriminating" was entirely an artifact of conditions
    passed in the wrong shape and quietly discarded.

    Returning None is NOT a skip. `query_fields` is authoritative: the
    translator lists every field this model's rules match or rewrite, so a name
    absent from it names something no rule looks at. Forcing nothing then
    answers the SAME question the condition asks, because every flow in the
    model already satisfies it. The stateless cloud model against a
    `related:0` check is exactly that (CLOUD_BENCH_PLAN.md §1.7.2). A field the
    translator CAN match but cannot yet force carries `scope: unsupported` and
    is refused here, so absence never has to stand in for "not implemented".
    """
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

    if recipes is None:
        raise ValueError(
            "query condition %r cannot be honoured: this payload carries no "
            "`query_fields`, so nothing says how -- or whether -- %r is "
            "represented in the model. Refused rather than guessed "
            "(AD6_PLAN.md §9.23.2a)." % (condition, name))

    recipe = recipes.get(name)
    if recipe is None:
        return None                     # the model constrains nothing here

    if recipe.get('scope') == 'unsupported':
        raise ValueError(
            "query condition %r cannot be honoured: %s"
            % (condition, recipe.get('why', 'no reason recorded')))

    return recipe


def _global_literals(recipe, value, condition):
    """ The shared bit-vector literals for a field ad6 represents GLOBALLY.

    MUST go through ad6's own converters. A global field's bits live in one
    vector for the whole model (`dst_port_<i>=<bit>`, `proto_<i>=<bit>`,
    `ip4_dst_<i>=<bit>`), and every rule's own condition expands into exactly
    those names -- so forcing them lands on the same variables the rules
    constrain. Rebuilding the names here instead would be a second copy of a
    naming convention, which is how the two drift.

    The PROTOCOL is looked up by name, never passed as a number. ad6's
    `CanonizeProto` looks its table up by name and silently returns the
    no-next-header code on a miss -- `CanonizeProto('6')` is 59, not 6 -- so a
    `RuleField`'s canonical '6' would force a bit pattern no rule ever matches.
    The translator ships the table it used for the model's own bits.
    """
    kind = recipe['kind']
    if kind == 'port':
        return list(XMLUtils.ConvertPortToVariables(str(value),
                                                    recipe['direction']))
    if kind == 'proto':
        name = (recipe.get('names') or {}).get(str(value))
        if name is None:
            raise ValueError(
                "query condition %r cannot be honoured: protocol %r has no "
                "name in ad6's IANA table (known: %s). It must NOT be passed "
                "through -- CanonizeProto silently returns the no-next-header "
                "code for anything it cannot look up, so an unmapped protocol "
                "becomes a wrong answer rather than an error."
                % (condition, value,
                   ', '.join(sorted((recipe.get('names') or {}).values()))))
        return list(XMLUtils.ConvertProtoToVariables(name))
    if kind == 'cidr':
        text = str(value)
        if '/' not in text:
            text = '%s/%d' % (text, 32 if recipe['version'] == '4' else 128)
        elem = et.fromstring(
            '<ip xmlns="http://config" version="%s" direction="%s">'
            '<address>%s</address></ip>'
            % (recipe['version'], recipe['direction'], text))
        XMLUtils.deannotate(elem)
        return list(XMLUtils.ConvertCIDRToVariables(
            XMLUtils.CanonizeIP(elem), recipe['direction']))
    raise ValueError(
        "query condition %r names a global field of unknown kind %r"
        % (condition, kind))


def _node_literals(recipe, value, node, condition):
    """ The per-node SSA bit literals for a field ad6 represents node-scoped.

    FORCED AT THE PROBE'S OWN NODE, because that is where FaVe evaluates a
    check's condition: `NetPlumberAdapter._create_compliance_rules` hands the
    vector to the PROBE, whose incoming source flows carry the header as it
    ARRIVES. For a field nothing rewrites the choice is immaterial -- the frame
    axiom makes every node on a realised path carry the same value -- but for a
    rewritten one only the probe is right, and this path must not have a
    different answer depending on whether the field happens to be mutable.
    """
    try:
        bits = XMLUtils.ValueToBitvector(value, recipe['width'])
    except Exception:
        raise ValueError(
            "malformed query condition %r: %r is neither an integer nor a "
            "ternary bit-vector, and a node-scoped field is compared against a "
            "fixed-width vector (AD6_PLAN.md §9.23.2a)."
            % (condition, value)) from None

    # A don't-care bit contributes NO literal -- the same rule the match side
    # follows (§9.35). Forcing it either way would narrow the question.
    return [XMLUtils.variable(
        XMLUtils.FieldBitName(recipe['field'], node, index), bit == '1')
        for index, bit in enumerate(bits) if bit != 'x']


def _negate(literals):
    """ The complement of a conjunction of literals, as one disjunction.

    WEAK ON PURPOSE, and it is the safe reading rather than a compromise.
    `_CreateBitConstraints` gives a global bit an AT-MOST-ONE constraint over
    its `=0`/`=1` pair and no at-least-one, so a bit the model never pins is
    genuinely free. Asserting "some bit IS the other value" would name
    variables that may not exist in the encoding at all, and a fresh variable
    carries no exclusion against the one the path forces -- the answer would
    come back satisfiable for the wrong reason. Negating only the literals a
    POSITIVE condition would have forced uses exactly the variables the model
    already has: where the path pins the field, every disjunct is false and the
    query is refuted; where it does not, a free bit admits a differing value
    and the disjunct is true, which is the right answer either way.
    """
    negated = []
    for literal in literals:
        flipped = deepcopy(literal)
        flipped.attrib[XMLUtils.ATTRNEGATED] = (
            'false' if flipped.attrib.get(XMLUtils.ATTRNEGATED) == 'true'
            else 'true')
        negated.append(flipped)
    return negated


def _condition_terms(cond, recipes, node, path="literal"):
    """ (units, clauses, vacuous) for a check's whole condition list.

    `units` are literals that must hold; `clauses` are disjunctions that must
    hold, one per NEGATED condition; `vacuous` names the conditions the model
    does not constrain, for the log -- they are honoured, and saying so out
    loud is what keeps "honoured because there is nothing there" distinct from
    "quietly dropped".
    """
    units = []
    clauses = []
    vacuous = []

    for condition in (cond or []):
        recipe = _condition_recipe(condition, recipes, path)
        if recipe is None:
            vacuous.append(condition.get("name"))
            continue

        value = condition.get("value")
        if recipe['scope'] == 'global':
            literals = _global_literals(recipe, value, condition)
        else:
            literals = _node_literals(recipe, value, node, condition)

        if not literals:
            # The value constrains nothing even though the field exists -- a
            # match-all CIDR, say. Same standing as an unconstrained field.
            vacuous.append(condition.get("name"))
            continue

        if condition.get("negated"):
            clauses.append(_negate(literals))
        else:
            units.extend(literals)

    _refuse_contradictions(units, cond)
    return units, clauses, vacuous


def _refuse_contradictions(units, cond):
    """ Two positive conditions that pin one bit to both values at once.

    Left alone this is not merely a contradictory question but a WRONGLY
    SATISFIABLE one. `_CreateBitConstraints` gives a global bit its
    at-most-one constraint only for the `=0`/`=1` pair the MODEL itself
    mentions, so a bit no rule pins gets two fresh, unrelated variables and
    both can be true at the same time. A check asking for two different ports
    at once is malformed; it is refused rather than answered.
    """
    pinned = {}
    for literal in units:
        name = literal.attrib[XMLUtils.ATTRNAME]
        if '=' in name:
            # A global bit: the NAME carries the value ("dst_port_3=1"), and
            # the same rstrip the bit constraints themselves key on.
            body, value = name.rstrip('01'), name[len(name.rstrip('01')):]
        else:
            # A node-scoped SSA bit: an ordinary boolean, value in the polarity.
            body = name
            value = literal.attrib.get(XMLUtils.ATTRNEGATED) != 'true'

        if body in pinned and pinned[body] != value:
            raise ValueError(
                "query conditions %r pin %s to both %r and %r at once. That is "
                "a contradictory question, and ad6's bit encoding would answer "
                "it SATISFIABLE rather than refute it, because the at-most-one "
                "constraint exists only between the values the model itself "
                "mentions." % (cond, body, pinned[body], value))
        pinned[body] = value


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
            extra_vars.extend(_seed_literals(
                q['src_cidr'], literal.get('query_fields'),
                _SRC_ADDRESS_FIELD['6' if ':' in q['src_cidr'] else '4'],
                source))
        units, clauses, vacuous = _condition_terms(
            q.get('cond'), literal.get('query_fields'), destination)
        extra_vars.extend(units)
        extra_clauses = clauses
        if vacuous:
            # Said out loud, every time. A condition honoured because the model
            # constrains nothing is a DIFFERENT thing from one quietly dropped,
            # and the only way that distinction survives into a run's record is
            # if the run says which fields it was.
            print("[ad6 bridge] %s -> %s: condition on %s is vacuous -- no "
                  "rule of this model matches or rewrites it" % (
                      q['source'], q['probe'], ', '.join(sorted(set(vacuous)))),
                  file=sys.stderr, flush=True)
        # NOTE (AD6_PLAN.md §5.5 C4 part 2, §9.9): there is deliberately no
        # probe-side VLAN forcing here. The semantic path had an opt-in
        # `probe_untag` that enforced a probe's declared arrival VLAN; a
        # probe accepts whatever the network delivers (owner
        # 2026-09-13), and a condition on a terminal rule would be silently
        # ignored anyway (§9.9.1) -- so forcing it would ask a different
        # question under the same name. Deleted with the rest of that path.
        if progress:
            start = time.time()
        reachable = session.Query(source, destination, extra_vars=extra_vars,
                                  extra_clauses=extra_clauses)
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
