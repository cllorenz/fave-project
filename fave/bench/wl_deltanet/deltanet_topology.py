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

""" The port-annotated topology, DERIVED from the traces (D3, §2.4).

**D3 was filed on a false premise, which this module corrects.** The plan --
and my own first reading of the data -- recorded that "a row names a router and
a next-hop and neither end's port, while FaVe's router model is port-based",
and called that the converter's real open question. It is not. **The ports are
in the data**, and a complete port-annotated topology comes out of it with
nothing invented.

The name `s<i>-<j>` is not a router. It is a **(switch, port) pair**, which is
the paper's own model: Delta-net's `link(r)` is "purposefully more general than
a pair of, say, ports", and it achieves that by SPLITTING a switch into one
graph node per input port its rules match -- "if a switch s contains rules that
can match three input ports, we encode s as three separate nodes" (§4.1), which
is why Table 2 reports 68 nodes for a 16-switch network. So `i` is the switch
and `j` the port, and both columns of every row name one.

Everything below is measured on the vendored traces, and every one of the
measurements is REFUSED rather than assumed, because each is a property of
these two files and not of the format:

  * the destination port is a function of `(source switch, destination switch)`
    -- one physical link per switch pair, so traffic from a given neighbour
    always lands on the same port;
  * at any switch, distinct neighbours occupy DISTINCT ports -- the
    neighbour-to-port map is injective, which is what makes it invertible;
  * the switch-level edge set is SYMMETRIC, so both ends of every link are
    known and the EGRESS port is recoverable: the port of `i` facing `k` is the
    port on which `i` receives from `k`;
  * a switch with degree d has exactly d+1 ports, numbered `1..d+1`;
  * port 1 is never an inter-switch destination. It is the external,
    border-router-facing port -- the paper connects each of the sixteen Open
    vSwitches to a Quagga border router (§4.2) -- and it is where traffic
    enters the modelled network;
  * no rule forwards within one switch, and none forwards back out the port it
    arrived on.

`homes()` answers the other half of what a reachability property needs: where
traffic LEAVES. A prefix's rules thin out towards one switch and stop, and the
node that receives the prefix without carrying a rule for it is the delivery
point. Every one of the 1,400 prefixes terminates at exactly one switch, and
14 switches home exactly 100 prefixes each -- which is the paper's "each border
router advertises one hundred IP prefixes" (§4.2), and incidentally accounts
for its 1,600 against the traces' 1,400: two well-connected switches home none
-- s8 at degree 7 and s9 at degree 6 -- and 2 x 100 is exactly the shortfall.
They are not the two BEST connected (s2 has degree 8 and homes its hundred), so
"pure transit" is a description of what they do here, not an explanation of why.
"""

from __future__ import annotations

import collections
import re

from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Set, Tuple

from bench.wl_deltanet.deltanet_trace import Insert


#: The port every switch reserves for its external border router.
EXTERNAL_PORT = 1

_NODE = re.compile(r'^s(?P<switch>\d+)-(?P<port>\d+)$')


class TopologyError(Exception):
    """ An invariant FaVe's port-based model needs, that the trace broke. """


class Topology(NamedTuple):
    """ What the trace says the network is wired like. """

    #: Switch ids, ascending.
    switches: List[int]
    #: Undirected inter-switch links, as `frozenset({i, k})`.
    links: Set[FrozenSet[int]]
    #: `(switch, neighbour) -> the port of `switch` that faces `neighbour`.
    port_of: Dict[Tuple[int, int], int]
    #: `switch -> every port it has`, including `EXTERNAL_PORT`.
    ports: Dict[int, Set[int]]

    def degree(self, switch: int) -> int:
        """ Inter-switch links at `switch` -- one fewer than its ports. """
        return sum(1 for link in self.links if switch in link)

    def neighbours(self, switch: int) -> List[int]:
        return sorted(k for (s, k) in self.port_of if s == switch)

    def egress_port(self, switch: int, towards: int) -> int:
        """ The port `switch` sends out of to reach `towards`.

        This is the whole point of the symmetry check: the trace never states
        an egress port, and it does not have to, because the port `switch`
        faces `towards` with is the port it RECEIVES from `towards` on.
        """
        try:
            return self.port_of[(switch, towards)]
        except KeyError:
            raise TopologyError(
                "s%d has no link to s%d, so it cannot forward there"
                % (switch, towards)) from None


def parse_node(name: str) -> Tuple[int, int]:
    """ `s12-3` -> `(12, 3)`: switch twelve, port three. """
    match = _NODE.match(name)
    if match is None:
        raise TopologyError(
            "%r is not an `s<switch>-<port>` node name. Every name in both "
            "vendored traces is, and the whole port model rests on it, so an "
            "unrecognised one is refused rather than filed somewhere." % name)
    return int(match.group('switch')), int(match.group('port'))


def derive_topology(inserts: Iterable[Insert]) -> Topology:
    """ The port-annotated topology, with every invariant checked. """
    inserts = list(inserts)

    # (source switch, destination switch) -> the ports it was seen landing on.
    landings: Dict[Tuple[int, int], Set[int]] = collections.defaultdict(set)
    ports: Dict[int, Set[int]] = collections.defaultdict(set)

    for insert in inserts:
        src_switch, src_port = parse_node(insert.router)
        dst_switch, dst_port = parse_node(insert.next_hop)

        if src_switch == dst_switch:
            raise TopologyError(
                "%s forwards to %s, within one switch. FaVe would model that "
                "as a device forwarding to itself; neither vendored trace "
                "does it." % (insert.router, insert.next_hop))
        if dst_port == EXTERNAL_PORT:
            raise TopologyError(
                "%s forwards to %s, an inter-switch link landing on port %d -- "
                "which both vendored traces reserve for the external border "
                "router, and which is what makes it the entry point."
                % (insert.router, insert.next_hop, EXTERNAL_PORT))

        landings[(src_switch, dst_switch)].add(dst_port)
        ports[src_switch].add(src_port)
        ports[dst_switch].add(dst_port)

    port_of: Dict[Tuple[int, int], int] = {}
    for (src_switch, dst_switch), seen in sorted(landings.items()):
        if len(seen) > 1:
            raise TopologyError(
                "traffic from s%d lands on ports %s of s%d. The port model "
                "assumes ONE link per switch pair, so the destination port is "
                "a function of the pair; it is not here."
                % (src_switch, sorted(seen), dst_switch, ))
        port_of[(dst_switch, src_switch)] = seen.pop()

    # Injective: two neighbours sharing a port would make `egress_port`
    # ambiguous in exactly the direction the trace does not state.
    by_switch: Dict[int, List[Tuple[int, int]]] = collections.defaultdict(list)
    for (switch, neighbour), port in port_of.items():
        by_switch[switch].append((neighbour, port))
    for switch, pairs in sorted(by_switch.items()):
        if len({port for _, port in pairs}) != len(pairs):
            raise TopologyError(
                "s%d receives from two neighbours on one port (%s), so the "
                "port cannot identify the link." % (switch, sorted(pairs)))

    links = {frozenset((switch, neighbour)) for (switch, neighbour) in port_of}
    for switch, neighbour in sorted(port_of):
        if (neighbour, switch) not in port_of:
            raise TopologyError(
                "s%d receives from s%d but never sends to it. The egress port "
                "is recovered from the reverse direction, so a one-way link "
                "leaves it unknown." % (switch, neighbour))

    topology = Topology(
        switches=sorted(ports), links=links,
        port_of=port_of, ports={s: set(p) for s, p in ports.items()})

    for switch in topology.switches:
        degree = topology.degree(switch)
        expected = set(range(EXTERNAL_PORT, degree + EXTERNAL_PORT + 1))
        if topology.ports[switch] != expected:
            raise TopologyError(
                "s%d has degree %d and ports %s, not the %s a switch with one "
                "external port and one port per neighbour would have."
                % (switch, degree, sorted(topology.ports[switch]),
                   sorted(expected)))

    for insert in inserts:
        src_switch, src_port = parse_node(insert.router)
        dst_switch, _ = parse_node(insert.next_hop)
        if topology.egress_port(src_switch, dst_switch) == src_port:
            raise TopologyError(
                "%s forwards to %s, back out the port it arrived on."
                % (insert.router, insert.next_hop))

    return topology


def homes(inserts: Iterable[Insert]) -> Dict[str, int]:
    """ `prefix -> the switch it is delivered at`.

    A node that RECEIVES a prefix without carrying a rule for it is where that
    prefix's traffic stops, which in this network is the switch whose border
    router advertised it. Refused if any prefix stops at more than one switch,
    because then "where traffic leaves" is not well defined and no edge-to-edge
    property can be stated over it.
    """
    carried: Dict[str, Set[str]] = collections.defaultdict(set)
    received: Dict[str, Set[str]] = collections.defaultdict(set)
    for insert in inserts:
        carried[insert.prefix].add(insert.router)
        received[insert.prefix].add(insert.next_hop)

    homed: Dict[str, int] = {}
    for prefix, nodes in sorted(carried.items()):
        terminal = received[prefix] - nodes
        switches = {parse_node(node)[0] for node in terminal}
        if len(switches) != 1:
            raise TopologyError(
                "%s is delivered at %d switches (%s), so it has no single "
                "egress and no edge-to-edge property can be stated over it."
                % (prefix, len(switches), sorted(switches)))
        homed[prefix] = switches.pop()

    return homed
