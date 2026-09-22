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

""" Reads a Delta-net NSDI'17 forwarding-update trace (CLOUD_BENCH_PLAN.md §2).

    +100.3.0.0/16,s10-1,s2-9,180

**D1, the fourth field, is settled and this module is where that lives.** The
plan required its meaning to be established BEFORE any converter was written,
because a column whose meaning is guessed at is a converter that is wrong in a
way nothing can notice. It is a PRIORITY ENCODING LONGEST-PREFIX MATCH:

    priority = 5 * prefix_length + 100

exactly, with no exception in either vendored trace -- 76,200 of 76,200 rows.
Longer prefix, higher priority, which is how Delta-net (and any OpenFlow-style
flat table) linearises LPM into a priority-ordered rule list.

**So the column carries no information of its own.** Everything it says is
already in the prefix, and a converter reads the prefix. That is a licence to
IGNORE it and simultaneously the reason not to do so silently: `PRIORITY` is
asserted on every row as it is parsed, so a future trace that encodes something
else -- an administrative distance, a metric, a timestamp -- is refused rather
than quietly read as an LPM tie-break it is not. The assertion costs one
comparison per row and is the only thing standing between D1's finding and the
next trace that does not share it.

The parser REFUSES what it does not recognise, rather than skipping it. A
skipped line is a rule that silently is not in the model, and a forwarding model
missing rules still answers every query -- just wrongly. The `-` withdrawal
these two files do not contain is refused for the same reason: `*-only-inserts`
is a claim about the data, and it is checked rather than trusted.
"""

from __future__ import annotations

import collections
import os
import re

from typing import Dict, Iterable, List, NamedTuple, Set, Tuple


HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'deltanet-traces')

#: The two traces in scope, in the order the plan names them (§2).
TRACES = ('airtel1-only-inserts.csv', 'airtel2-only-inserts.csv')

#: D1: `priority = PRIORITY_SLOPE * prefix_length + PRIORITY_BASE`.
PRIORITY_SLOPE = 5
PRIORITY_BASE = 100

_LINE = re.compile(
    r'^(?P<op>[-+])'
    r'(?P<prefix>(?:\d{1,3}\.){3}\d{1,3}/(?P<plen>\d{1,2})),'
    r'(?P<router>[^,]+),'
    r'(?P<next_hop>[^,]+),'
    r'(?P<priority>\d+)$')


class TraceError(Exception):
    """ A line this module will not guess at. """


def lpm_priority(plen: int) -> int:
    """ The priority D1 found the traces encode a prefix length as. """
    return PRIORITY_SLOPE * plen + PRIORITY_BASE


class Insert(NamedTuple):
    """ One forwarding rule, as the trace states it. """
    prefix: str
    plen: int
    router: str
    next_hop: str
    priority: int


def parse_trace(lines: Iterable[str], name: str = '<trace>') -> List[Insert]:
    """ Every row of a trace, or an exception naming the row that stopped it. """
    inserts: List[Insert] = []
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        match = _LINE.match(line)
        if match is None:
            raise TraceError(
                "%s:%d: not a Delta-net update -- expected "
                "`+<prefix>,<router>,<next_hop>,<priority>`, read %r"
                % (name, number, line))

        if match.group('op') != '+':
            raise TraceError(
                "%s:%d: a WITHDRAWAL in a file named only-inserts. The static "
                "snapshot (CLOUD_BENCH_PLAN.md §2.1) rests on the trace having "
                "none, so this is refused rather than replayed: %r"
                % (name, number, line))

        plen = int(match.group('plen'))
        priority = int(match.group('priority'))
        if priority != lpm_priority(plen):
            raise TraceError(
                "%s:%d: the fourth field is %d, and D1 established it as "
                "%d*%d+%d = %d for a /%d. This trace encodes something else in "
                "it, and no converter here reads it: settle what, before "
                "reading this file. Line: %r"
                % (name, number, priority, PRIORITY_SLOPE, plen, PRIORITY_BASE,
                   lpm_priority(plen), plen, line))

        inserts.append(Insert(
            prefix=match.group('prefix'), plen=plen,
            router=match.group('router'), next_hop=match.group('next_hop'),
            priority=priority))

    return inserts


def read_trace(path: str) -> List[Insert]:
    """ `parse_trace` over a file, named by it so an error is locatable. """
    with open(path) as handle:
        return parse_trace(handle, os.path.basename(path))


def final_fib(inserts: Iterable[Insert]) -> Dict[Tuple[str, str], Insert]:
    """ Replay the inserts into the forwarding state they leave behind.

    Keyed by `(router, prefix)`, which is what makes the replay meaningful --
    and, in these two traces, what makes it trivial: no key is ever written
    twice (`collisions` is 0), so no rule supersedes another and the result
    does not depend on the order. That is a MEASURED property of the vendored
    traces, not a property of the format, so it is measured rather than assumed
    and `collisions` is reported in the census.
    """
    fib: Dict[Tuple[str, str], Insert] = {}
    for insert in inserts:
        fib[(insert.router, insert.prefix)] = insert
    return fib


def collisions(inserts: Iterable[Insert]) -> int:
    """ How many inserts overwrite a `(router, prefix)` an earlier one set. """
    seen: Set[Tuple[str, str]] = set()
    repeats = 0
    for insert in inserts:
        key = (insert.router, insert.prefix)
        if key in seen:
            repeats += 1
        seen.add(key)
    return repeats


def edges(inserts: Iterable[Insert]) -> Set[Tuple[str, str]]:
    """ The directed `router -> next_hop` pairs the trace names. """
    return {(i.router, i.next_hop) for i in inserts}


def priority_histogram(inserts: Iterable[Insert]) -> Dict[int, int]:
    """ Rules per prefix length -- D1's evidence, and the LPM depth profile. """
    return dict(collections.Counter(i.plen for i in inserts))
