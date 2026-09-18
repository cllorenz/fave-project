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

""" Reader for the NoD cloud dataset's transfer function (CLOUD_BENCH_PLAN.md §1).

The file is Hassel transfer-function syntax -- the same `$`-separated shape
`wl_stanford` uses -- but it differs from `wl_stanford`'s in two ways that matter
and that nothing in the file declares:

  1. **The header layout is different.** See `CLOUD_MAPPING` and §1.1: the field
     order was recovered by measuring which of the 128 bit positions the 2,941
     rules constrain, not read from a spec. Both layouts happen to put
     `packet.ipv4.destination` at bit 48, so a reader using the wrong one still
     produces plausible forwarding and goes wrong only on the ACL and NAT
     fields. `test/test_cloud_tf.py` pins it for that reason.

  2. **There are no `link$` lines.** Ports are NODES, not interfaces: a rule
     `fwd A -> B` means "a packet at node A moves to node B", which is the same
     `R_<node>` relation set the dataset's `.smt2` queries declare. The topology
     is therefore implicit in shared node ids and has to be DERIVED. That is
     `classify_nodes`, and the evidence it is right is that its census
     reproduces `cloud-tf/README.txt`'s generator parameters exactly (5
     datacenters, 8 leaf routers each, 30 hosts per leaf) while the `.tf` file
     states none of them.

This module does the reading and the derivation only. Turning the result into
FaVe's model is `cloud_preparation.py`.
"""

from __future__ import annotations

import enum
import json

from typing import Dict, Iterable, List, Optional, Union


# CLOUD_BENCH_PLAN.md §1.1. Bit offsets into the 128-bit match string, in FaVe's
# own field vocabulary, so this dict IS the workload's `mapping.json`.
# `packet.ipv6.proto` is FaVe's name for the protocol byte even on IPv4 -- see
# `wl_stanford/stanford-json/mapping.json`, which does the same.
CLOUD_MAPPING: Dict[str, int] = {
    'packet.ether.vlan': 0,
    'packet.ipv4.source': 16,
    'packet.ipv4.destination': 48,
    'packet.ipv6.proto': 80,
    'packet.upper.sport': 88,
    'packet.upper.dport': 104,
    'packet.upper.tcp.flags': 120,
    'length': 128,
}

_FIELD_SIZES: Dict[str, int] = {
    'packet.ether.vlan': 16,
    'packet.ipv4.source': 32,
    'packet.ipv4.destination': 32,
    'packet.ipv6.proto': 8,
    'packet.upper.sport': 16,
    'packet.upper.dport': 16,
    'packet.upper.tcp.flags': 8,
}

_IP_FIELDS = ('packet.ipv4.source', 'packet.ipv4.destination')

# The node-id arithmetic of §1.2, derived from the id structure and confirmed
# against the README: each datacenter occupies a 100000-wide id block; the block
# base is the core; every leaf router then owns 62 consecutive ids -- ingress,
# egress, then 30 (receive, transmit) host pairs.
_DC_BLOCK = 100000
_LEAF_SPAN = 62
_INTERNET_BLOCK = 1500000


class NodeRole(enum.Enum):
    """ What a node is, derived from which side of a rule it appears on. """

    #: appears as a rule in-port, i.e. it has rules of its own
    DEVICE = 'device'
    #: only ever an in-port of rules that take traffic elsewhere: it injects
    SOURCE = 'source'
    #: only ever an out-port: traffic ends here
    SINK = 'sink'


class Rule:
    """ One `fwd`/`rw` line of a transfer function. """

    __slots__ = ('action', 'in_ports', 'out_ports', 'match', 'mask', 'rewrite', 'name')

    def __init__(self, action, in_ports, out_ports, match, mask, rewrite, name):
        self.action = action
        self.in_ports = in_ports
        self.out_ports = out_ports
        self.match = match
        self.mask = mask
        self.rewrite = rewrite
        self.name = name

    @property
    def is_drop(self) -> bool:
        """ A rule with no out-port discards. 45 of the dataset's rules do. """
        return not self.out_ports

    def __eq__(self, other):
        if not isinstance(other, Rule):
            return NotImplemented
        return all(
            getattr(self, s) == getattr(other, s) for s in Rule.__slots__)

    def __repr__(self):
        return "Rule(%s, %s -> %s, %s)" % (
            self.action, self.in_ports, self.out_ports, self.name)


def _ports(field: str) -> List[int]:
    if field in ('', 'None'):
        return []
    return [int(p) for p in json.loads(field)]


def _optional(field: str) -> Optional[str]:
    return None if field == 'None' else field


def parse_tf(lines: Iterable[str]) -> List[Rule]:
    """ The `fwd`/`rw` rules of a transfer function, in file order.

    File order is load-bearing downstream: a transfer function is evaluated
    first-match-wins, and `bench/np_preparation.py`'s LPM re-prioritisation
    reorders a declared FIB *relative to the order it is given*.
    """
    rules = []

    for line in lines:
        line = line.rstrip('\n')
        if not (line.startswith('fwd') or line.startswith('rw')):
            continue

        fields = line.split('$')
        # action$in$match$mask$rewrite$_$_$out$...$name$
        rules.append(Rule(
            action=fields[0],
            in_ports=_ports(fields[1]),
            out_ports=_ports(fields[7]),
            match=fields[2],
            mask=_optional(fields[3]),
            rewrite=_optional(fields[4]),
            name=fields[12],
        ))

    return rules


def read_match_field(
        match: str, field: str) -> Optional[Union[str, int]]:
    """ One field of a match string, or None when it is fully wildcarded.

    IP fields come back as CIDR, everything else as an integer -- the two forms
    `bench/np_preparation.py`'s `_CONVERSION` already uses, so a caller can hand
    the result straight to the FaVe model.
    """
    start = CLOUD_MAPPING[field]
    bits = match[start:start + _FIELD_SIZES[field]]

    if set(bits) == {'x'}:
        return None

    if field in _IP_FIELDS:
        prefix_len = len(bits) - bits.count('x')
        value = int(bits.replace('x', '0'), 2)
        return '%s/%d' % (
            '.'.join(str((value >> shift) & 0xff) for shift in (24, 16, 8, 0)),
            prefix_len
        )

    return int(bits.replace('x', '0'), 2)


def node_name(node: int) -> str:
    """ A readable name for a node id.

    Names, not ids, are what a compliance report is read with, so the arithmetic
    of §1.2 is spelled out here once: `dc<n>_core`, `dc<n>_leaf<k>_{in,out}`,
    `dc<n>_leaf<k>_host<h>_{rx,tx}`, and the two internet endpoints.
    """
    if node >= _INTERNET_BLOCK:
        return 'internet_gw' if node == _INTERNET_BLOCK else 'internet_rx'

    block = node // _DC_BLOCK
    datacenter = block - 10
    offset = node % _DC_BLOCK

    if offset == 0:
        return 'dc%d_core' % datacenter

    leaf, within = divmod(offset - 1, _LEAF_SPAN)

    if within == 0:
        return 'dc%d_leaf%d_in' % (datacenter, leaf)
    if within == 1:
        return 'dc%d_leaf%d_out' % (datacenter, leaf)

    host, side = divmod(within - 2, 2)
    return 'dc%d_leaf%d_host%d_%s' % (
        datacenter, leaf, host, 'rx' if side == 0 else 'tx')


class NodeModel:
    """ The derived taxonomy of §1.2: which nodes are devices, sources, sinks. """

    def __init__(self, rules: List[Rule]) -> None:
        self._rules_at: Dict[int, List[Rule]] = {}
        targets = set()

        for rule in rules:
            for port in rule.in_ports:
                self._rules_at.setdefault(port, []).append(rule)
            targets.update(rule.out_ports)

        # A node with rules of its own is a forwarding element -- including one
        # whose only rule DROPS and which therefore never appears as anybody's
        # out-port. The alternative test ("appears on both sides") would
        # misfile such a node as a traffic source.
        has_rules = set(self._rules_at)

        #: nodes that carry rules: the tables of the FaVe model
        self.devices = sorted(n for n in has_rules if self._forwards_onward(n))
        #: nodes whose single rule only injects: the generators
        self.sources = sorted(has_rules - set(self.devices))
        #: nodes that only ever receive: the probes
        self.sinks = sorted(targets - has_rules)

    def _forwards_onward(self, node: int) -> bool:
        """ True when the node acts on traffic rather than merely originating it.

        A source's rule set is exactly one rule that hands traffic to its
        router under a source-address constraint; anything else -- several
        rules, a drop, a rewrite, or a match on the destination -- is a device.
        """
        rules = self._rules_at[node]
        if len(rules) != 1:
            return True

        rule = rules[0]
        if rule.action != 'fwd' or rule.is_drop:
            return True

        return read_match_field(rule.match, 'packet.ipv4.source') is None

    def role(self, node: int) -> NodeRole:
        if node in set(self.devices):
            return NodeRole.DEVICE
        if node in set(self.sources):
            return NodeRole.SOURCE
        return NodeRole.SINK

    def rules_at(self, node: int) -> List[Rule]:
        return self._rules_at.get(node, [])


def classify_nodes(rules: List[Rule]) -> NodeModel:
    """ The node taxonomy of CLOUD_BENCH_PLAN.md §1.2. """
    return NodeModel(rules)
