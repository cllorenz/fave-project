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

""" The topology of a trace that names ROUTERS, not ports (CLOUD_BENCH_PLAN.md
§2.15).

    +43.245.208.0/24,17,20,3583901

Every archive member outside airtel names bare devices -- `17`, `20` -- and no
port anywhere (§2.14, D3). `topology.py` cannot read them, correctly: its whole
derivation rests on `s<i>-<j>` being a `(switch, port)` pair. This module is
the other reading, and it differs in the one place that matters.

**THE PORTS ARE INVENTED HERE, and `topology.py` invents none.** A router gets
port 1 for its border network -- `topology.EXTERNAL_PORT`, the same convention
-- and then one port per neighbour, numbered 2, 3, ... in ascending neighbour
order. That is a RENAMING of the adjacency, not a guess at it: every link the
rules use gets exactly one port at each end, and no port exists that no rule
uses. But which port number faces which neighbour is ours, so it is stamped
(`PORT_ASSIGNMENT`) and nothing may read meaning into it.

What IS refused, because the model needs it and the data might not give it:

  * a name that is not a decimal router id -- the only form `berkeley` uses;
  * a router forwarding to itself;
  * an asymmetric adjacency: a link used in one direction only would get a
    port at one end that nothing at the other end faces.

The two measured properties that make `berkeley` so simple -- every chain is
ONE hop, and the adjacency is a complete graph less one link (§2.15 (b), (c))
-- are deliberately NOT asserted. Nothing in the model depends on them, and a
second port-free trace should not be refused for having transit.
"""

from __future__ import annotations

import collections
import re

from typing import Dict, Iterable, List, Set, Tuple

from bench.deltanet.topology import EXTERNAL_PORT, Topology, TopologyError, homes
from bench.deltanet.trace import Insert


#: What the stamp says about where the port numbers came from.
PORT_ASSIGNMENT = ('invented: port %d is the border network, then one port per '
                   'neighbour in ascending neighbour order' % EXTERNAL_PORT)

_ROUTER = re.compile(r'^[0-9]+$')


def parse_router(name: str) -> int:
    """ `17` -> router 17. """
    if _ROUTER.match(name) is None:
        raise TopologyError(
            "%r is not a decimal router id, which is the only form the "
            "port-free traces read here use" % name)
    return int(name)


def derive_router_topology(inserts: Iterable[Insert]) -> Topology:
    """ One port per neighbour, with the adjacency checked. """
    neighbours: Dict[int, Set[int]] = collections.defaultdict(set)
    for insert in inserts:
        router = parse_router(insert.router)
        next_hop = parse_router(insert.next_hop)
        if router == next_hop:
            raise TopologyError(
                "router %d forwards %s to itself" % (router, insert.prefix))
        neighbours[router].add(next_hop)
        neighbours.setdefault(next_hop, set())

    one_way: List[Tuple[int, int]] = sorted(
        (a, b) for a, peers in neighbours.items() for b in peers
        if a not in neighbours[b])
    if one_way:
        raise TopologyError(
            "%d router pair(s) forward in one direction only, e.g. %d -> %d. "
            "A port is assigned per LINK, so a one-way pair would leave one "
            "end facing nothing." % (len(one_way), one_way[0][0], one_way[0][1]))

    port_of: Dict[Tuple[int, int], int] = {}
    ports: Dict[int, Set[int]] = {}
    for router, peers in neighbours.items():
        for rank, peer in enumerate(sorted(peers)):
            port_of[(router, peer)] = EXTERNAL_PORT + 1 + rank
        ports[router] = set(range(EXTERNAL_PORT, EXTERNAL_PORT + len(peers) + 1))

    return Topology(
        switches=sorted(neighbours),
        links={frozenset((a, b)) for (a, b) in port_of},
        port_of=port_of, ports=ports)


def router_homes(inserts: Iterable[Insert]) -> Dict[str, int]:
    """ `prefix -> the router it is delivered at` -- `topology.homes`, whose
    rule (the node that receives a prefix without carrying it) needs no ports. """
    return homes(inserts, switch_of=parse_router)


def router_rule(insert: Insert, topology: Topology) -> Tuple[int, Tuple[int, ...], int]:
    """ `(router, in-ports, egress port)` for one row, for `build_model`.

    In-ports are EMPTY -- any port -- because the row names none: a FIB entry
    here does not care where a packet came from, and qualifying it by every
    port would state the same thing 23 times over.
    """
    router = parse_router(insert.router)
    return router, (), topology.egress_port(router, parse_router(insert.next_hop))
