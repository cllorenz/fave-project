#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" Which generated check carries which third-party verdict (CLOUD_BENCH_PLAN.md §1.9.0).

THE PROBLEM THIS SOLVES. Compiling the five-rule policy yields 71 checks. Six of
them correspond to a `.smt2` instance whose verdict was produced outside this
repository; the other 65 are expectations WE derived from a policy we wrote. Put
in one list they are indistinguishable, and a mistake in our own understanding
would then read exactly as authoritative as the external verdicts -- the
self-confirming failure §1.8 exists to prevent.

A DROPPED VERDICT MUST BE LOUD. The hand-built check set this replaces had the
opposite property: a check that went missing still counted as agreement, because
nothing had violated it. So `pair_oracle_to_checks` REFUSES unless every query
matches exactly one check. A query that matches none has stopped being tested;
one that matches several is ambiguous, and picking either would be a guess about
which question the dataset answered.

A POLICY IS AN INTENT, SO A VERDICT IS NOT A PASS. A check asserts reachability
or its absence; the oracle says whether the pair is reachable. The two agree or
they do not, and where they do not the EXPECTED outcome is a violation -- which
is how query 06 is reproduced (see `reach.txt`). `expected_violated` is that
comparison, and nothing else in this workload may decide it.
"""

from __future__ import annotations

import re

from typing import Any, Dict, FrozenSet, List, Sequence, Set, Tuple

from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from util.packet_util import canonicalize_field_value


#: Dropped from both sides before comparing. Every conditional check
#: `reach_csv_to_checks` emits carries `related:0`, and the cloud model has no
#: conntrack at all -- the dataset's ACLs are stateless -- so the condition
#: constrains nothing here and corresponds to nothing in any `.smt2` instance.
#: Keeping it would make every conditional check unmatchable. Spelled once and
#: applied to both the OXM name a check line carries and the FaVe field name a
#: report renders, which for this field are the same string
#: (`OXM_FIELD_TO_MATCH_FIELD['related'] == 'related'`).
_IGNORED = frozenset({'related'})

#: One constraint: the FaVe field, its canonical value, and whether the check
#: asks for that value or for anything but it.
Constraint = Tuple[str, Any, bool]


def _constraint(name: str, value: str, negated: bool) -> Constraint:
    """ One `field:value` token as a comparable triple.

    Both sides go through `canonicalize_field_value`, the same normalisation
    `RuleField` applies, so `protocol:tcp` from a service declaration and
    `ip_proto=6` from a Datalog instance are the SAME constraint rather than two
    spellings that happen to mean one thing.
    """
    field = OXM_FIELD_TO_MATCH_FIELD[name]
    return (field, canonicalize_field_value(field, str(value)), negated)


def query_constraints(query: Dict[str, Any]) -> FrozenSet[Constraint]:
    """ What a `.smt2` instance constrains, as comparable triples.

    `fields` are the constants its source relation pins (`tcp_dst=332`);
    `conditions` are its negated guards (`!tcp_dst:331`), which cannot be a
    generator header and become check conditions instead (see
    `cloud_oracle.parse_instance`).
    """
    out = []

    for field in query.get('fields', []):
        name, _, value = field.partition('=')
        if name in _IGNORED:
            continue
        out.append(_constraint(name, value, False))

    for condition in query.get('conditions', []):
        negated = condition.startswith('!')
        name, _, value = condition.lstrip('!').partition(':')
        if name in _IGNORED:
            continue
        out.append(_constraint(name, value, negated))

    return frozenset(out)


def check_constraints(check: str) -> FrozenSet[Constraint]:
    """ What a generated check line constrains, as comparable triples. """
    out = []
    for token in check.split():
        if not token.startswith('f='):
            continue
        name, _, value = token[2:].partition(':')
        negated = name.startswith('!')
        name = name.lstrip('!')
        if name in _IGNORED:
            continue
        out.append(_constraint(name, value, negated))
    return frozenset(out)


def check_endpoints(check: str) -> Tuple[str, str, bool]:
    """ (source, probe, must_reach) of a generated check line. """
    source = probe = None
    must_reach = True
    for token in check.split():
        if token == '!':
            must_reach = False
        elif token.startswith('s='):
            source = token[2:]
        elif token.startswith('p='):
            probe = token[2:]
    if source is None or probe is None:
        raise ValueError("check names no source/probe pair: %r" % check)
    return source, probe, must_reach


def _matches(query_set: FrozenSet[Constraint],
             check_set: FrozenSet[Constraint]) -> bool:
    """ Does `check_set` ask the query's question?

    Subset rather than equality, because an FPL service declares a PROTOCOL
    where some instances constrain only a port: query 05 asks about `tcp_dst =
    350` and `S350` compiles to `protocol:tcp;port:350`. The surplus must be
    POSITIVE, which is what makes the narrowing sound in both directions -- a
    narrower must-reach check that passes proves the broader question
    satisfiable, and a narrower must-not-reach check is implied by the broader
    unreachability. A surplus NEGATION would do neither, so it is not a match.
    """
    if not query_set <= check_set:
        return False
    return not any(negated for _f, _v, negated in check_set - query_set)


class UnmatchedQuery(Exception):
    """ An oracle verdict no generated check carries, or several do. """


def pair_oracle_to_checks(
        queries: Sequence[Dict[str, Any]],
        checks: Sequence[str],
        endpoint_of: Dict[int, str]
) -> List[Dict[str, Any]]:
    """ One record per oracle query: the check that carries it, and whether
    that check is expected to be violated.

    `endpoint_of` maps a `.smt2` node id to the FPL role member's name
    (`cloud_endpoints`), which is what turns a query's bare node ids into the
    `source.<name>`/`probe.<name>` a check addresses.

    Raises `UnmatchedQuery` rather than returning a partial answer: a verdict
    that is not carried by exactly one check is not being tested, and reporting
    it as reproduced is the vacuity defect this whole module exists to close.
    """
    parsed = [(c, check_endpoints(c), check_constraints(c)) for c in checks]
    records = []

    for query in queries:
        source = endpoint_of.get(query['source'])
        target = endpoint_of.get(query['target'])
        if source is None or target is None:
            raise UnmatchedQuery(
                "%s names node %s -> %s, and the model instantiates no "
                "endpoint for %s. The policy must name every endpoint the "
                "oracle asks about, or that verdict is untested."
                % (query['name'], query['source'], query['target'],
                   'the source' if source is None else 'the target'))

        wanted = query_constraints(query)
        candidates = [
            (line, endpoints) for line, endpoints, constraints in parsed
            if endpoints[0] == 'source.%s' % source
            and endpoints[1] == 'probe.%s' % target
            and _matches(wanted, constraints)
        ]

        if len(candidates) != 1:
            raise UnmatchedQuery(
                "%s (%s -> %s, constraints %s) matches %d generated checks, "
                "not 1. %s\nCandidates: %s"
                % (query['name'], source, target, sorted(wanted),
                   len(candidates),
                   "The policy no longer asks this query's question, so its "
                   "verdict would be reported as reproduced without being "
                   "tested." if not candidates else
                   "Which of them the dataset answered cannot be decided here.",
                   [line for line, _e in candidates] or '(none)'))

        line, (_source, _probe, must_reach) = candidates[0]
        reachable = query['expect'] == 'sat'

        records.append({
            'name': query['name'],
            'smt2': query['smt2'],
            'sha256': query['sha256'],
            'expect': query['expect'],
            'check': line,
            'must_reach': must_reach,
            # The policy states an INTENT. Where it disagrees with the
            # dataset -- q06 asserts a permission the network does not grant --
            # the reproduction IS the violation.
            'expected_violated': must_reach != reachable,
        })

    return records


#: A violation line and the condition bullets under it, as
#: `reporting/reporter.py` renders them for BOTH engine paths -- the
#: `get_compliance_results()` one and the net_plumber log one, which is why
#: only the shape they share is matched here.
_VIOLATION = re.compile(
    r'^- `(?P<source>[^`]+)` (?P<direction>reaches|does not reach) '
    r'`(?P<probe>[^`]+)`')
_CONDITION = re.compile(r'^\s+- (?P<name>[^=]+)=')


#: A check's identity as a REPORT can state it: who, to whom, in which
#: direction, constrained on which fields. Not the condition VALUES: a
#: complement expands to several vectors and a violated one renders as a bit
#: pattern, so the values a report shows are per-vector rather than per-check.
#: Verified unique across every generated check by test_cloud_provenance.py --
#: if a future policy makes two checks share a key, that test fails rather than
#: this module quietly attributing one check's violation to another.
Key = Tuple[str, str, bool, FrozenSet[str]]


def check_key(check: str) -> Key:
    """ The report-level identity of a generated check line. """
    source, probe, must_reach = check_endpoints(check)
    return (source, probe, must_reach,
            frozenset(field for field, _v, _n in check_constraints(check)))


def parse_violations(text: str) -> Set[Key]:
    """ The checks `report.md` reports a violation for.

    Reads the rendered report because that is the only place a NetPlumber run's
    per-check verdict exists: `get_compliance_results()` is implemented by the
    ad6 and APKeep adapters and NOT by `NetPlumberAdapter`, so the log-derived
    report is the shared source of truth (reporter.py's `_engine_violations`).

    A must-reach check that was violated reads "does not reach" and a
    must-not-reach one reads "reaches", so the DIRECTION in the line is the
    polarity of the check, not of the finding.
    """
    violations: Set[Key] = set()
    current: Any = None
    fields: Set[str] = set()

    def _flush() -> None:
        if current is not None:
            violations.add((current[0], current[1], current[2], frozenset(fields)))

    for line in text.splitlines():
        match = _VIOLATION.match(line)
        if match:
            _flush()
            fields = set()
            current = (
                match.group('source'), match.group('probe'),
                match.group('direction') == 'does not reach')
            continue
        condition = _CONDITION.match(line)
        if condition and current is not None:
            name = condition.group('name').strip()
            # Dropped on this side too, and for the same reason as in
            # `check_constraints`: `related` says nothing about a stateless
            # model, and a key that carried it here but not there would match
            # nothing at all.
            if name not in _IGNORED:
                fields.add(name)

    _flush()
    return violations
