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

""" The Delta-net snapshot as a FaVe model (CLOUD_BENCH_PLAN.md §2.4).

**The port structure is NOT invented here, and that is the difference from
`wl_cloud`.** `cloud_preparation` has to say "THE PORT STRUCTURE IS INVENTED,
AND THAT IS THE RISK", because the NoD transfer function states forwarding as
node-to-node rules with no interfaces at all. This dataset states them as
`s<switch>-<port>`, so every device, port and link below is read off the data
(`deltanet_topology.py`), and a mis-wiring is a derivation bug rather than a
modelling choice nothing can contradict.

Each switch becomes one device with two FaVe ports per Delta-net port -- an
in-port and an out-port -- because a FaVe link joins an out-port to an in-port
and the trace's ports are bidirectional. Port 1 is the external,
border-router-facing port: the generator hangs off its in-port and the probe
off its out-port, so "traffic entering the network at switch i" and "traffic
leaving it at switch j" are exactly what a check about roles i and j asks.

**THE DELIVERY RULES ARE SYNTHESISED, AND THEY ARE THE ONE INVENTION.** The
trace carries inter-switch forwarding and nothing else: a prefix's rules thin
towards its home switch and simply stop, which is how `deltanet_topology.homes`
identifies the home in the first place. A packet therefore arrives at the home
switch and dies, and no probe anywhere can see it. So for each prefix this
module adds one rule at its home switch forwarding it out port 1, which is what
SDN-IP installs in the real network and what the data set omits.

Three things keep that honest rather than convenient:

  * it is DERIVED, from the homing, which is itself cross-checked against the
    paper's "each border router advertises one hundred IP prefixes";
  * it SHADOWS NOTHING -- measured: no prefix has a single rule at its own home
    switch, on any port, in either trace, so nothing is overridden;
  * it is COUNTED separately in the census and stamped in the result, because a
    rule total that silently mixes 38,100 read rules with 1,400 invented ones
    is exactly the figure nobody can audit later.

Rule order is longest-prefix-first within each device, which is what makes this
a FIB rather than a list: NetPlumber resolves priority by rule index (see
`np_preparation._reprioritise_fib_lpm` for the bug that costs). Only two of the
1,400 prefixes nest inside another, so the ordering is load-bearing for exactly
those two -- which is a reason to get it right, not a reason to skip it.
"""

from __future__ import annotations

import collections

from typing import Any, Dict, Iterable, List, Sequence, Tuple

from devices.abstract_device import LPM
from bench.wl_deltanet.deltanet_topology import (
    EXTERNAL_PORT, Topology, parse_node)
from bench.wl_deltanet.deltanet_trace import Insert


#: Ports are numbered `switch * _PORT_SPAN (+ _OUT_OFFSET) + port`, so every
#: FaVe port reads back to its switch and its Delta-net port by eye. The widest
#: switch has 8 neighbours, hence 9 ports.
_PORT_SPAN = 100
_OUT_OFFSET = 50

#: One device per switch, one table per device.
#
#: The stage prefix every device name carries, and the declaration
#: `_reprioritise_fib_lpm` reads to decide which tables have LPM semantics.
#: `wl_cloud` is the precedent for declaring it as a constant rather than in a
#: `config.json`: that file belongs to the raw-table JSON path, which reads it
#: while converting vendored Hassel tables, and this workload's input is two
#: CSVs.
#:
#: ONE STAGE, and the declaration is therefore trivial -- it says "all of
#: them". That is worth saying out loud rather than letting a reader infer it
#: is doing work: `wl_cloud`'s equivalent is load-bearing because it EXCLUDES
#: its NAT gateway, whose /32 rewrites must not be reordered by prefix length,
#: and there is nothing here to exclude. Every device in this model is a FIB,
#: every rule in it forwards, and one stage is also the more honest reading of
#: the original benchmark, which models one flat forwarding table per node.
#:
#: What the declaration DOES buy is that there is one LPM mechanism in the tree
#: rather than two. A per-workload sort is how `_reprioritise_fib_lpm`'s own
#: predecessor came to do nothing at all on wl_i2, leaving 3,731 rules shadowed
#: behind a containing prefix.
STAGE_SWITCH = 'sw'
TABLE_TYPES = [STAGE_SWITCH]
FIB_TABLE_TYPES = [STAGE_SWITCH]

_DEVICE_PREFIX = STAGE_SWITCH
_SOURCE_PREFIX = 'source'
_PROBE_PREFIX = 'probe'


def device_name(switch: int) -> str:
    return '%s.s%d' % (_DEVICE_PREFIX, switch)


def endpoint_name(switch: int) -> str:
    """ What the FPL inventory calls the network behind switch `switch`. """
    return 's%d' % switch


def in_port(switch: int, port: int) -> int:
    return switch * _PORT_SPAN + port


def out_port(switch: int, port: int) -> int:
    return switch * _PORT_SPAN + _OUT_OFFSET + port


def _port_name(switch: int, number: int) -> str:
    return '%s.%d' % (device_name(switch), number)


def build_model(
        inserts: Iterable[Insert],
        topology: Topology,
        homed: Dict[str, int],
) -> Dict[str, Any]:
    """ The four artifacts `GenericBenchmark` reads, from the trace. """
    inserts = list(inserts)

    devices: List[Sequence[Any]] = []
    for index, switch in enumerate(topology.switches, start=1):
        ports = sorted(topology.ports[switch])
        devices.append((
            device_name(switch), 'switch',
            [str(in_port(switch, p)) for p in ports]
            + [str(out_port(switch, p)) for p in ports],
            {device_name(switch): index},
            # DECLARE the forwarding table longest-prefix-match on the model
            # itself (TABLE_SEMANTICS_PLAN.md S3b), so the adapters order it
            # rather than depending on `_reprioritise_fib_lpm` having done so at
            # generation time. Keyed `<node>.1`, SwitchModel's own table name.
            {'%s.1' % device_name(switch): LPM},
        ))

    links: List[Sequence[Any]] = []
    for link in sorted(topology.links, key=sorted):
        left, right = sorted(link)
        links.append((_port_name(left, out_port(left, topology.egress_port(left, right))),
                      _port_name(right, in_port(right, topology.egress_port(right, left))),
                      False))
        links.append((_port_name(right, out_port(right, topology.egress_port(right, left))),
                      _port_name(left, in_port(left, topology.egress_port(left, right))),
                      False))

    # (in-ports, prefix, egress) per device, so transit and delivery rules go
    # into one table and are ordered together by prefix length.
    table: Dict[int, List[Tuple[Tuple[int, ...], str, int]]] = (
        collections.defaultdict(list))

    for insert in inserts:
        switch, port = parse_node(insert.router)
        neighbour, _ = parse_node(insert.next_hop)
        table[switch].append(
            ((port,), insert.prefix, topology.egress_port(switch, neighbour)))

    delivered = 0
    for prefix, switch in sorted(homed.items()):
        # ONE rule per prefix, over every INTER-SWITCH in-port: a FIB entry does
        # not care which neighbour a packet came from. The external in-port is
        # deliberately excluded -- a packet arriving from the border router for
        # a network behind that same border router would be sent straight back
        # out of it, and a hairpin is not something this data set states. It
        # only affects the self-pair, which is not a network question here and
        # which `reach_csv_to_checks` does not emit for these roles anyway.
        ingress = tuple(sorted(
            p for p in topology.ports[switch] if p != EXTERNAL_PORT))
        table[switch].append((ingress, prefix, EXTERNAL_PORT))
        delivered += 1

    routes: List[Sequence[Any]] = []
    for index, switch in enumerate(topology.switches, start=1):
        # Emitted in a deterministic base order; `_reprioritise_fib_lpm` below
        # does the longest-prefix-first pass. Its sort is STABLE, so the order
        # within one prefix length is exactly this one.
        entries = sorted(table[switch], key=lambda entry: (entry[1], entry[0]))
        for rule, (ingress, prefix, egress) in enumerate(entries, start=1):
            routes.append((
                device_name(switch), index, rule,
                ['ipv4_dst=%s' % prefix],
                ['fd=%s' % _port_name(switch, out_port(switch, egress))],
                [_port_name(switch, in_port(switch, port)) for port in ingress],
            ))

    # LPM is DECLARED on each device above, not repaired here: the positional
    # backends order a declared table themselves (TABLE_SEMANTICS_PLAN.md S3a),
    # so the rule index no longer has to carry the prefix-length rank.

    # `_reprioritise_fib_lpm` rewrites each rule's INDEX and leaves the list in
    # emission order, so afterwards the two disagree. That is safe -- the
    # adapter hands NetPlumber `rule.idx`, never a list position, which is what
    # wl_stanford's independently validated 165 pairs rest on -- but it leaves
    # an artifact whose order invites a reader, or a future adapter, to take
    # position for priority. Sorting by the index costs nothing and removes the
    # question; it also keeps `routes.json` byte-identical to the hand-sorted
    # version this replaced, which is how the refactor was shown to be inert.
    order = {switch: rank for rank, switch in enumerate(topology.switches)}
    routes.sort(key=lambda route: (order[int(route[0].split('.s')[1])], route[2]))

    sources: List[Sequence[Any]] = []
    source_links: List[Sequence[Any]] = []
    probes: List[Sequence[Any]] = []
    probe_links: List[Sequence[Any]] = []
    for switch in topology.switches:
        name = endpoint_name(switch)
        # The destination is what this network forwards on, so the generator
        # constrains nothing else: "every packet that could enter here".
        sources.append(
            ('%s.%s' % (_SOURCE_PREFIX, name), 'generator', ['ipv4_dst=0.0.0.0/0']))
        source_links.append((
            '%s.%s.1' % (_SOURCE_PREFIX, name),
            _port_name(switch, in_port(switch, EXTERNAL_PORT)), True))
        probes.append(
            ('%s.%s' % (_PROBE_PREFIX, name), 'probe', 'existential',
             None, None, None, None))
        probe_links.append((
            _port_name(switch, out_port(switch, EXTERNAL_PORT)),
            '%s.%s.1' % (_PROBE_PREFIX, name), False))

    return {
        'topology': {'devices': devices, 'links': links},
        'routes': routes,
        'sources': {'devices': sources, 'links': source_links},
        'probes': {'devices': probes, 'links': probe_links},
        'census': {
            'devices': len(devices),
            'links': len(links),
            'transit_rules': len(inserts),
            'delivery_rules': delivered,
            'rules': len(routes),
            'sources': len(sources),
            'probes': len(probes),
        },
    }
