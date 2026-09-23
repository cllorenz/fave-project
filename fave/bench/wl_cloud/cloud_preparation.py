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

""" Builds FaVe's model from the cloud transfer function (CLOUD_BENCH_PLAN.md §1.3).

WHY THIS IS NOT `bench/np_preparation.py`. That module's port arithmetic encodes
`wl_stanford`'s conventions -- `port // 100000` is a table id, `intervals` map
the remainder onto an in/mid/out pipeline stage, and `_probe_id_to_name` /
`_source_id_to_name` decode Stanford's id scheme -- and its `add_source` path
hardcodes an unconstrained `ipv4_dst=0.0.0.0/0` generator. The cloud dataset has
neither a three-stage pipeline nor unconstrained sources: its generators carry
the host's own `/30`. What IS reused, because it is generic: the LPM
re-prioritisation, which was measured a complete no-op here and is gone.

THE PORT STRUCTURE IS INVENTED, AND THAT IS THE RISK. The dataset states
forwarding as node-to-node rules: it has no interfaces and no `link$` lines
(§1.2). FaVe needs ports and links, so this module gives every device one
in-port and one out-port per distinct neighbour, and joins each out-port to the
neighbour's in-port. Nothing in the source data would catch that going wrong --
a mis-wired port yields a model that builds cleanly and answers a different
question -- so `test/test_cloud_preparation.py` pins it.

Keying every rule of a device to a single in-port is faithful rather than a
simplification: the transfer function keys its rules by NODE, not by arriving
interface, so no rule in the dataset can distinguish where a packet came in.
"""

from __future__ import annotations

import json
import os

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bench.wl_cloud.cloud_endpoints import Endpoint
from bench.wl_cloud.cloud_tf import (
    CLOUD_MAPPING,
    NodeModel,
    Rule,
    node_name,
    read_match_field,
)


# FaVe's short field names, in the order a match clause should read.
_SHORT_NAMES: List[Tuple[str, str]] = [
    ('packet.ether.vlan', 'vlan'),
    ('packet.ipv4.source', 'ipv4_src'),
    ('packet.ipv4.destination', 'ipv4_dst'),
    ('packet.ipv6.proto', 'ip_proto'),
    ('packet.upper.sport', 'tcp_src'),
    ('packet.upper.dport', 'tcp_dst'),
    ('packet.upper.tcp.flags', 'tcp_flags'),
]

#: The stage prefix each node class becomes. `fib_tables` reads the
#: prefix of a device name to decide which tables are FIBs, so the classes that
#: do destination routing must be separable by name from the one that does NAT.
STAGE_CORE = 'core'
STAGE_LEAF_IN = 'lin'
STAGE_LEAF_OUT = 'lout'
STAGE_GATEWAY = 'gw'

TABLE_TYPES = [STAGE_CORE, STAGE_LEAF_IN, STAGE_LEAF_OUT, STAGE_GATEWAY]

#: The gateway is excluded: its rules are /32 NAT matches, not a routing table,
#: and re-ordering them by prefix length would reorder NAT against NAT.
FIB_TABLE_TYPES = [STAGE_CORE, STAGE_LEAF_IN, STAGE_LEAF_OUT]

#: Ports are allocated `device_index * _PORT_SPAN + offset`, which keeps every
#: port readable back to its device. The widest device has 31 neighbours.
_PORT_SPAN = 1000

_INTERNET_GW = 1500000


def _stage(node: int) -> str:
    if node >= _INTERNET_GW:
        return STAGE_GATEWAY
    if node % 100000 == 0:
        return STAGE_CORE
    return STAGE_LEAF_IN if node % 2 == 1 else STAGE_LEAF_OUT


def device_name(node: int) -> str:
    """ `<stage>.<node name>` -- the form FaVe's device registry and the FIB
    declaration both read. """
    name = node_name(node)
    # A leaf router's two nodes are one device name under different stages
    # (`lin.dc0_leaf0` / `lout.dc0_leaf0`), and the gateway would otherwise
    # stutter as `gw.internet_gw`.
    if name.endswith(('_in', '_out', '_gw')):
        name = name.rsplit('_', 1)[0]
    return '%s.%s' % (_stage(node), name)


def _match_fields(match: str) -> List[str]:
    fields = []
    for field, short in _SHORT_NAMES:
        value = read_match_field(match, field)
        if value is not None:
            fields.append('%s=%s' % (short, value))
    return fields


def _rewrite_action(rule: Rule) -> Optional[str]:
    """ `rw=<field>:<value>;...` for the fields the rule's mask clears.

    MASK POLARITY. Hassel applies a rewrite as `(h & mask) | rewrite`
    (`wl_stanford/stanford-hassel/headerspace/tf.py`), so a `0` in the mask
    marks a bit the rule REPLACES. That is what this dataset does -- its 28 `rw`
    rules clear exactly one 32-bit address field each (§1.1) -- and it is the
    INVERSE of what `np_preparation._get_rewrite` looks for, which tests the
    field's mask for all-ones. Both readers are right about their own input:
    `wl_stanford`'s committed `stanford-json/*.tf.json` carries inverted masks.
    See CLOUD_BENCH_PLAN.md §1.6 for the trap that creates.

    THE PREFIX LENGTH IS PART OF THE VALUE. The DNAT rules rewrite the
    destination to a /24 SERVICE SUBNET, not to a host: `10.0.0.0/24` leaves
    the low 8 bits free. Emitting the bare address instead pins traffic to one
    host and every internet-sourced query answers "unreachable" -- which is
    exactly how this was found (§1.6).
    """
    assignments = []

    for field, short in _SHORT_NAMES:
        start = CLOUD_MAPPING[field]
        width = _width(field)
        if set(rule.mask[start:start + width]) != {'0'}:
            continue
        value = read_match_field(rule.rewrite, field)
        if value is None:
            continue
        assignments.append('%s:%s' % (short, value))

    return 'rw=%s' % ';'.join(assignments) if assignments else None


def _width(field: str) -> int:
    offsets = sorted(v for k, v in CLOUD_MAPPING.items() if k != 'length')
    start = CLOUD_MAPPING[field]
    following = [o for o in offsets if o > start]
    return (following[0] if following else CLOUD_MAPPING['length']) - start


class _Ports:
    """ The invented port structure: one in-port per device, one out-port per
    (device, neighbour) pair. """

    def __init__(self, devices: Sequence[int]) -> None:
        self._base = dict(
            (node, (index + 1) * _PORT_SPAN)
            for index, node in enumerate(devices))
        self._out: Dict[Tuple[int, int], int] = {}
        self._next: Dict[int, int] = dict((node, 1) for node in devices)

    def in_port(self, node: int) -> int:
        return self._base[node]

    def out_port(self, node: int, target: int) -> int:
        key = (node, target)
        if key not in self._out:
            self._out[key] = self._base[node] + self._next[node]
            self._next[node] += 1
        return self._out[key]

    def declared(self, node: int) -> List[str]:
        return [str(self.in_port(node))] + [
            str(port) for (owner, _t), port in sorted(self._out.items())
            if owner == node
        ]

    def links(self) -> List[Tuple[int, int, int]]:
        """ (owner, target, out-port) for every allocated out-port. """
        return [(o, t, p) for (o, t), p in sorted(self._out.items())]


class RoleEndpoint:
    """ One FPL role's presence at one leaf router (CLOUD_BENCH_PLAN.md §1.9.6).

    The policy's roles are the dataset's 25 SERVICES plus the Internet, and a
    service's hosts sit behind one to nine leaf routers, so a role is not one
    place in the model. It is this: a generator that injects the leaf's address
    block carrying the service's own source port, and a probe that observes
    everything that leaf delivers to its hosts.

    BOTH constraints are load-bearing, and for the same reason. A leaf's /25 can
    belong to TWO services (services 2 and 3 are both 10.0.17.0/25), which the
    data plane separates only by TCP port: a rule permitting service j names
    `sport = 331+j` on the way in and `dport = 331+j` on the way out. Drop the
    generator's source port and service 3's traffic satisfies service 2's ACL,
    manufacturing reachability the matrix denies. The probe cannot carry the
    mirror-image filter -- `netplumber/adapter.py` has `filter_fields` commented
    out -- so the destination half is qualified in the CHECK instead, by
    `reach_csv_to_checks --deny-per-service`.
    """

    __slots__ = ('name', 'inject', 'fields', 'observe')

    def __init__(
            self,
            name: str,
            inject: int,
            fields: Sequence[str],
            observe: Sequence[int]
    ) -> None:
        self.name = name
        self.inject = inject
        self.fields = list(fields)
        self.observe = sorted(observe)

    @property
    def source_device(self) -> str:
        return 'source.%s' % self.name

    @property
    def probe_device(self) -> str:
        return 'probe.%s' % self.name


def leaf_blocks(model: NodeModel) -> Dict[int, str]:
    """ {leaf ingress node: the /25 it is responsible for}.

    Read off the DATACENTER CORE's routing table -- one `fwd <prefix> -> <leaf>`
    rule per leaf -- because that is the network stating where a prefix lives,
    rather than inferred from the leaf's own drop rule. The two agree on all 40
    leaves and `test_cloud_preparation.py` pins that they do; a disagreement
    would mean the derivation had drifted from one of its two witnesses.
    """
    blocks: Dict[int, str] = {}

    for node in model.devices:
        if _stage(node) != STAGE_CORE:
            continue
        for rule in model.rules_at(node):
            prefix = read_match_field(rule.match, 'packet.ipv4.destination')
            if prefix is None:
                continue
            for target in rule.out_ports:
                if _stage(target) == STAGE_LEAF_IN:
                    blocks[target] = prefix

    return blocks


def role_endpoints(
        model: NodeModel,
        router_services: Dict[int, Sequence[int]],
        service_port: Any,
        endpoint_name: Any,
        internet_name: str,
) -> List[RoleEndpoint]:
    """ One `RoleEndpoint` per (service, leaf) pair, plus the Internet.

    `router_services` is the README's own `Services of router <id>` census and
    `service_port` its port algebra, both from `cloud_readme.py`; the callables
    are passed in rather than imported so this module keeps knowing only about
    the transfer function.
    """
    blocks = leaf_blocks(model)
    sinks = set(model.sinks)

    # Which sinks does each device deliver to? A leaf's egress node feeds its
    # own hosts; the internet egress is fed from all five cores.
    delivers: Dict[int, List[int]] = {}
    for node in model.devices:
        for rule in model.rules_at(node):
            for target in rule.out_ports:
                if target in sinks:
                    delivers.setdefault(node, []).append(target)

    # The Internet injects AT the gateway (which holds the inbound NAT) and is
    # observed at the egress sink, which is a different node -- and one fed
    # from all five datacenter cores, so the probe carries five links.
    endpoints = [RoleEndpoint(
        internet_name, _INTERNET_GW, [],
        [sink for sink in sinks if sink >= _INTERNET_GW],
    )]

    for leaf in sorted(router_services):
        if leaf not in blocks:
            raise ValueError(
                "leaf %s carries services %s but no core routes a prefix to "
                "it: the README and the transfer function disagree about "
                "which leaf routers exist"
                % (node_name(leaf), sorted(router_services[leaf])))

        for index in sorted(router_services[leaf]):
            endpoints.append(RoleEndpoint(
                endpoint_name(index, leaf),
                leaf,
                ['ipv4_src=%s' % blocks[leaf],
                 'tcp_src=%d' % service_port(index)],
                delivers.get(leaf + 1, []),
            ))

    return endpoints


def build_model(
        rules: List[Rule],
        model: NodeModel,
        endpoints: Optional[Iterable[int]] = None,
        role_members: Optional[Sequence[Any]] = None
) -> Dict[str, Any]:
    """ FaVe's topology / routes / sources / probes for a cloud transfer function.

    Two ways to name the model's endpoints, and they are alternatives:

      * `endpoints` restricts which source and sink NODES are instantiated;
      * `role_members` replaces both the generators and the probes with one of
        each per FPL ROLE MEMBER, which is what a policy-driven phase needs.

    The full dataset has 1,200 generators and 1,201 probes, and every generator
    costs a full flow propagation whether or not a check asks about it, so no
    phase instantiates more than its policy names.

    ONE NAME PER ROLE MEMBER IS A REQUIREMENT, NOT A CONVENIENCE.
    `bench/reach_csv_to_checks.py` writes `s=source.<name>` and
    `p=probe.<name>` from the same inventory entry, so a model that named the
    two sides of a host differently could not be addressed by a policy at all
    (see cloud_endpoints.Endpoint).

    A MEMBER IS A NAME, A PLACE TO INJECT, AND THE PLACES IT IS OBSERVED AT --
    `inject`, `fields` and `observe`. `cloud_endpoints.Endpoint` is the simple
    case (one sink, no header constraint) and `RoleEndpoint` the general one: a
    role of the 26x26 matrix is a SERVICE, spread over one to nine leaf routers
    and separated from the service sharing its address block only by a TCP
    port. Both satisfy the same three attributes, so there is one code path
    here rather than one per caller.
    """
    devices = list(model.devices)

    members = list(role_members) if role_members is not None else None

    wanted = set(endpoints) if endpoints is not None else None
    ports = _Ports(devices)

    routes: List[Tuple[Any, ...]] = []

    # Allocate out-ports in rule order, so a device's ports read in the order
    # its rules mention them.
    for node in devices:
        table = device_name(node)
        for index, rule in enumerate(model.rules_at(node), start=1):
            actions = []

            if rule.action == 'rw':
                rewrite = _rewrite_action(rule)
                if rewrite:
                    actions.append(rewrite)

            for target in rule.out_ports:
                actions.append('fd=%s.%d' % (table, ports.out_port(node, target)))

            routes.append((
                table,
                1,
                index,
                _match_fields(rule.match),
                actions,
                ['%s.%d' % (table, ports.in_port(node))],
            ))

    # NO LPM RE-PRIORITISATION HERE, and that is a decision rather than an
    # omission (TABLE_SEMANTICS_PLAN.md §0.6 / §2.8). 45 of this dataset's
    # devices hold ONE table mixing forwarding and filtering -- `lin.dc1_leaf0`
    # permits `10.0.4.0/25` on tcp/332, drops the rest of `10.0.4.0/25`, then
    # forwards everything else. Those two rules share a prefix and disagree, so
    # longest-prefix-match cannot resolve them at all: only their ORDER can, and
    # the permit must come first. The table is first-match, written in
    # destination-prefix terms.
    #
    # The repair that used to run here was measured a COMPLETE no-op: with it
    # removed the generated routes are byte-identical (1,741 rules), because the
    # colliding rules tie on prefix length and the default sorts last anyway. So
    # this workload declares no `lpm` table and orders nothing.

    topology: Dict[str, List[Any]] = {'devices': [], 'links': []}
    for index, node in enumerate(devices, start=1):
        name = device_name(node)
        topology['devices'].append(
            (name, 'switch', ports.declared(node), {name: index}))

    sources: Dict[str, List[Any]] = {'devices': [], 'links': []}
    probes: Dict[str, List[Any]] = {'devices': [], 'links': []}

    device_set = set(devices)
    source_set = set(model.sources)
    probe_names: set = set()

    # Which probes observe a sink. One per sink when each member names its own,
    # but a sink may be observed by SEVERAL, because two services can share a
    # leaf's address block and therefore its hosts (services 2 and 3 are both
    # 10.0.17.0/25). Those probes see identical flows, which is exactly why the
    # check set has to name the port -- see `RoleEndpoint`.
    observers: Dict[int, List[str]] = {}
    if members is not None:
        for member in members:
            for sink in member.observe:
                observers.setdefault(sink, []).append(member.probe_device)

    for owner, target, port in ports.links():
        src = '%s.%d' % (device_name(owner), port)

        if target in device_set:
            topology['links'].append(
                (src, '%s.%d' % (device_name(target), ports.in_port(target)), False))
            continue

        # A sink: the traffic ends here, so the port feeds a probe. A sink may
        # be targeted from SEVERAL devices -- the internet egress is reached
        # from all five datacenter cores -- so the probe is declared once and
        # linked from each of them.
        if members is not None:
            for name in observers.get(target, []):
                if name not in probe_names:
                    probe_names.add(name)
                    probes['devices'].append(
                        (name, 'probe', 'existential', None, None, None, None))
                probes['links'].append((src, '%s.1' % name, False))
            continue

        if wanted is not None and target not in wanted:
            continue
        name = 'probe.%s' % node_name(target)
        if name not in probe_names:
            probe_names.add(name)
            probes['devices'].append(
                (name, 'probe', 'existential', None, None, None, None))
        probes['links'].append((src, '%s.1' % name, False))

    def _inject(name: str, node: int, fields: List[str]) -> None:
        """ Attach a generator to whichever device receives traffic from `node`.

        A host transmit node hands its traffic to its leaf router, so the
        generator attaches THERE and inherits the node's own `/30` constraint.
        The internet gateway is itself a device (it holds the inbound NAT
        rules), so a generator naming it attaches to the gateway directly --
        nothing else can put traffic into it.
        """
        if node in source_set:
            rule = model.rules_at(node)[0]
            target = rule.out_ports[0]
            fields = _match_fields(rule.match) + fields
        elif node in device_set:
            target = node
        else:
            raise ValueError(
                "%s is a sink: nothing can be injected there" % node_name(node))

        # An unconstrained generator is spelled as the all-addresses match
        # rather than as an empty field list, which is how every other
        # workload in the suite spells it (`np_preparation.prepare_benchmark`).
        sources['devices'].append(
            (name, 'generator', fields or ['ipv4_dst=0.0.0.0/0']))
        sources['links'].append(
            ('%s.1' % name, '%s.%d' % (device_name(target), ports.in_port(target)),
             True))

    if members is not None:
        # A member's `fields` qualify its GENERATOR. They are empty for an
        # endpoint the policy addresses by name alone -- under an FPL policy a
        # header constraint belongs to the check, not to the injector, which is
        # what lets several questions share one generator. They are NOT empty
        # where two roles share an address block and the data plane tells them
        # apart by port: there the constraint decides which role the traffic
        # belongs to, and no check could add it afterwards (see `RoleEndpoint`).
        for member in members:
            _inject(member.source_device, member.inject, member.fields)
    else:
        for node in model.sources:
            if wanted is not None and node not in wanted:
                continue
            _inject('source.%s' % node_name(node), node, [])

    return {
        'topology': topology,
        'routes': routes,
        'sources': sources,
        'probes': probes,
        'ports': ports,
    }


def write_model(model: Dict[str, Any], files: Dict[str, str]) -> None:
    """ Writes the four artifacts `GenericBenchmark` reads. """
    for key, payload in (
            ('topology', model['topology']),
            ('routes', model['routes']),
            ('sources', model['sources']),
            ('policies', model['probes']),
    ):
        path = files[key]
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, 'w') as out:
            out.write(json.dumps(payload, indent=2) + '\n')
