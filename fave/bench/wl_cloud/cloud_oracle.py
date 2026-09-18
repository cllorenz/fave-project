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

""" Derives wl_cloud's oracle from the dataset's own Datalog instances.

`oracle.json` is what makes this workload a correctness GATE rather than a
reachability report: it carries six verdicts produced outside this repository,
each labelled sat or unsat in its own `.smt2` filename by a tool that predates
this tree by a decade.

IT IS DERIVED, NEVER WRITTEN BY HAND. The first version was transcribed by eye
out of `grep` output, and a single mistyped node id would have produced a wrong
oracle that FaVe then "agreed" with -- a self-confirming result with nothing
able to notice. The same failure is visible elsewhere in this tree:
`wl_stanford/stanford-json/*.tf.json` cannot be regenerated from the
`stanford-tfs/*.tf` beside it (inverted rewrite masks), so which of the two is
authoritative is now unanswerable. A derived artifact with no derivation is a
measurement resting on somebody's eyesight.

Two properties follow, and both are tested:

  * **The argument order is read out of each file, not assumed.** A `(query
    (R_n a b c ...))` line names the relation's variables positionally, so the
    instance states its own convention; hardcoding one would mis-assign every
    constant if another scenario ordered them differently.

  * **Anything not fully understood is refused.** A half-parsed query weakens
    the gate without changing its shape -- it still looks like six checks.
"""

from __future__ import annotations

import hashlib
import os
import re

from typing import Any, Dict, List, Optional


class Smt2ParseError(Exception):
    """ An instance this module will not guess about. """


#: Datalog variable name -> FaVe's short field name. A constrained variable
#: absent from this map is an error, never a skip: dropping it would WIDEN the
#: query, the direction that reports reachable what is not.
_FIELDS: Dict[str, str] = {
    'ip_src': 'ipv4_src',
    'ip_dst': 'ipv4_dst',
    'tcp_src': 'tcp_src',
    'tcp_dst': 'tcp_dst',
    'vlan': 'vlan',
    'ip_proto': 'ip_proto',
    'tcp_ctrl': 'tcp_flags',
}

_VERDICTS = ('sat', 'unsat')

_QUERY = re.compile(r'\(query\s+\(R_(\d+)([^()]*)\)\s*\)')
_BARE_SOURCE = re.compile(r'\(rule\s+\(R_(\d+)([^()]*)\)\s*\)')
_GUARDED_SOURCE = re.compile(
    r'\(rule\s+\(=>\s+\(and\s+\(init[^()]*\)\s+'
    r'\(not\s+\(=\s+(\w+)\s+\#x([0-9A-Fa-f]+)\)\)\s*\)\s*'
    r'\(R_(\d+)', re.S)


def _verdict(filename: str) -> str:
    parts = os.path.basename(filename).split('.')
    if len(parts) != 3 or parts[2] != 'smt2' or parts[1] not in _VERDICTS:
        raise Smt2ParseError(
            "%r does not name its verdict: expected '<n>.{sat,unsat}.smt2', "
            "which is the ONLY place the dataset records it" % filename)
    return parts[1]


def _field(var: str, filename: str) -> str:
    if var not in _FIELDS:
        raise Smt2ParseError(
            "%s constrains %r, which has no FaVe field. Refused rather than "
            "dropped: a dropped constraint widens the query." % (filename, var))
    return _FIELDS[var]


def parse_instance(filename: str, text: str) -> Dict[str, Any]:
    """ One `.smt2` instance -> the query it states.

    `filename` supplies the verdict and is used in error messages; `text` is
    the file's content.
    """
    query = _QUERY.search(text)
    if not query:
        raise Smt2ParseError("%s has no (query ...) form" % filename)

    target = int(query.group(1))
    order = query.group(2).split()

    fields: List[str] = []
    conditions: List[str] = []
    source: Optional[int] = None

    # Form 1: a bare source relation whose constant arguments are the
    # constraints, e.g. (rule (R_1500000 ip_src ip_dst tcp_src #x014C ...)).
    for match in _BARE_SOURCE.finditer(text):
        args = match.group(2).split()
        if len(args) != len(order):
            continue
        variables = [a for a in args if not a.startswith('#x')]
        if variables != [o for o, a in zip(order, args) if not a.startswith('#x')]:
            raise Smt2ParseError(
                "%s: the source relation names its arguments %r where the "
                "query names them %r. The argument order is read from the "
                "file, so a disagreement has no safe reading."
                % (filename, args, order))
        source = int(match.group(1))
        for name, arg in zip(order, args):
            if arg.startswith('#x'):
                fields.append('%s=%d' % (_field(name, filename), int(arg[2:], 16)))
        break

    # Form 2: a guarded source, whose guard is a NEGATED equality. That cannot
    # become a generator header -- a generator carries values, not complements
    # -- so it becomes a condition on the check instead.
    if source is None:
        guarded = _GUARDED_SOURCE.search(text)
        if guarded:
            source = int(guarded.group(3))
            conditions.append('!%s:%d' % (
                _field(guarded.group(1), filename), int(guarded.group(2), 16)))

    if source is None:
        raise Smt2ParseError(
            "%s states no source relation this module recognises (neither a "
            "bare (rule (R_n ...)) nor a negated-guard (rule (=> ...)))"
            % filename)

    return {
        'smt2': os.path.basename(filename),
        'source': source,
        'target': target,
        'fields': fields,
        'conditions': conditions,
        'expect': _verdict(filename),
    }


def derive_oracle(raw_dir: str) -> Dict[str, Any]:
    """ The oracle for every `.smt2` instance in `raw_dir`, in filename order.

    Each query records the sha256 of the instance it came from, so a result
    file can name the exact bytes its verdicts were taken from.
    """
    instances = sorted(f for f in os.listdir(raw_dir) if f.endswith('.smt2'))
    if not instances:
        raise Smt2ParseError("no .smt2 instances under %s" % raw_dir)

    queries = []
    for name in instances:
        path = os.path.join(raw_dir, name)
        raw = open(path, 'rb').read()
        query = parse_instance(name, raw.decode('utf-8'))
        query['name'] = 'q%s' % name.split('.')[0]
        query['sha256'] = hashlib.sha256(raw).hexdigest()
        queries.append(query)

    return {
        'derived_from': os.path.basename(raw_dir.rstrip('/')),
        'derived_by': 'bench/wl_cloud/cloud_oracle.py',
        'note': (
            "GENERATED -- do not edit. The verdict of each query is the one "
            "its .smt2 filename carries, i.e. the dataset's own, produced "
            "outside this repository. Prose about what each query asks lives "
            "in CLOUD_BENCH_PLAN.md 1.4."),
        'queries': queries,
    }
