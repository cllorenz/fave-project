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

""" Which border network reaches which, by walking the MODEL's own rules
(CLOUD_BENCH_PLAN.md §2.15).

A reference implementation of the forwarding semantics the engines are asked
to compute, deliberately small and deliberately naive: for every region of the
address space, start at each source's external port and follow the rules until
the packet leaves at a probe, is dropped, or loops. It reads `build_model`'s
output, not the trace, so a converter bug is in its input -- this is a check on
the ENGINES and on the matrix, the way `test_deltanet_lpm._walk` is, only over
every address rather than one per nested pair.

**Why `wl_berkeley` needs it and airtel did not.** Airtel's matrix follows from
the homing alone, and the walk agrees with it (validated on both traces:
`test_deltanet_fib_walk.py`). Berkeley's does not. Its rules are one hop to the
egress, but a router with no rule for a prefix falls back to the longest
CONTAINING prefix it does carry, and that sends some packets through a third
router: 23 reaches 22 although the two share no link, and nine routers reach
their own border network by a hairpin through a neighbour. None of those cells
can be stated from the homing, so the policy is stated from this walk instead.

The semantics, all of them the model's:

  * a device's rules are tried longest prefix first, ties by index -- the
    DECLARED `LPM` of `build_model` -- and a rule applies only on its
    `in_ports`, an empty list meaning any port;
  * a region is the set of addresses whose containing prefixes are exactly one
    prefix and its ancestors. Every address in it is forwarded alike by every
    rule, so one walk per region and source covers the whole space. Prefixes
    here nest or are disjoint, which is what makes the regions well defined;
  * an address in no prefix matches no rule anywhere and is dropped, so it
    reaches nothing and needs no walk.

`resolve='shortest'` inverts the priority, which is §3's LPM guard: if the
matrix does not change, the matrix cannot see LPM.
"""

from __future__ import annotations

import collections

from typing import Any, Dict, List, Optional, Set, Tuple


LOOP = 'loop'


def _net(prefix: str) -> Tuple[int, int]:
    address, _, length = prefix.partition('/')
    a, b, c, d = (int(octet) for octet in address.split('.'))
    return (a << 24) | (b << 16) | (c << 8) | d, int(length)


def regions(prefixes) -> List[List[str]]:
    """ One `[prefix, parent, grandparent, ...]` chain per non-empty region.

    A prefix whose addresses are all covered by longer prefixes has no region
    of its own and is skipped; it still appears in its descendants' chains.
    """
    nets = {p: _net(p) for p in prefixes}
    order = sorted(nets, key=lambda p: nets[p])
    parent: Dict[str, Optional[str]] = {}
    covered: Dict[str, int] = collections.defaultdict(int)
    stack: List[str] = []
    for prefix in order:
        start, length = nets[prefix]
        while stack:
            top_start, top_length = nets[stack[-1]]
            if start < top_start + (1 << (32 - top_length)):
                break
            stack.pop()
        parent[prefix] = stack[-1] if stack else None
        if stack:
            covered[stack[-1]] += 1 << (32 - length)
        stack.append(prefix)

    chains = []
    for prefix in order:
        if covered[prefix] >= 1 << (32 - nets[prefix][1]):
            continue
        chain = [prefix]
        while parent[chain[-1]] is not None:
            chain.append(parent[chain[-1]])
        chains.append(chain)
    return chains


def reachability(model: Dict[str, Any], resolve: str = 'lpm'
                 ) -> Dict[Tuple[str, str], int]:
    """ `{(source endpoint, probe endpoint): regions reaching it}`, over every
    region and every source; `(source, LOOP)` counts looping regions. """
    if resolve not in ('lpm', 'shortest'):
        raise ValueError("unknown resolution %r" % resolve)

    table: Dict[str, Dict[str, List[Tuple[int, Optional[frozenset], str]]]] = (
        collections.defaultdict(lambda: collections.defaultdict(list)))
    for device, _tid, index, match, actions, in_ports in model['routes']:
        prefix = match[0].split('=', 1)[1]
        table[device][prefix].append((
            index, frozenset(in_ports) if in_ports else None,
            actions[0].split('=', 1)[1]))
    for rules in table.values():
        for entries in rules.values():
            entries.sort(key=lambda entry: entry[0])

    links = {link[0]: link[1] for link in model['topology']['links']}
    delivered = {link[0]: link[1].split('.')[1]
                 for link in model['probes']['links']}
    starts = [(link[0].split('.')[1], link[1])
              for link in model['sources']['links']]
    hop_limit = 2 * len(model['topology']['devices']) + 2

    prefixes = {p for rules in table.values() for p in rules}
    reached: Dict[Tuple[str, str], int] = collections.Counter()
    for chain in regions(prefixes):
        if resolve == 'shortest':
            chain = chain[::-1]
        for source, entry in starts:
            port = entry
            for _hop in range(hop_limit):
                device = port.rsplit('.', 1)[0]
                rules = table[device]
                egress = next(
                    (egress for prefix in chain for _i, ports, egress
                     in rules.get(prefix, ()) if ports is None or port in ports),
                    None)
                if egress is None:
                    break                                   # dropped
                if egress in delivered:
                    reached[(source, delivered[egress])] += 1
                    break
                if egress not in links:
                    break                                   # dangling port
                port = links[egress]
            else:
                reached[(source, LOOP)] += 1
    return dict(reached)


def reached_pairs(reached: Dict[Tuple[str, str], int]) -> Set[Tuple[str, str]]:
    """ The `(source, probe)` endpoint pairs some region reaches. """
    return {pair for pair in reached if pair[1] != LOOP}
