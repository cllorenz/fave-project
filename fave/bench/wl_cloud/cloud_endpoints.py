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

""" The endpoints an FPL role can name (CLOUD_BENCH_PLAN.md §1.9).

WHY THIS EXISTS AT ALL. The dataset models a host as TWO nodes -- a transmit
node that injects and a receive node that absorbs -- and FaVe's policy layer
names ONE thing per role: `bench/reach_csv_to_checks.py` writes
`s=source.<name>` and `p=probe.<name>` from the same inventory entry. So the two
node ids have to be folded back into the single name the role carries, which is
what an `Endpoint` is.

IT IS DERIVED, never listed. The pairing comes out of `cloud_tf.node_name`'s own
arithmetic -- a host's rx and tx nodes differ only in their `_rx`/`_tx` suffix --
and each endpoint's address is read from the transmit node's own rule, which is
the same `/30` the generator will inherit. A hand-written table of node ids is
precisely what §1.8 forbids: it would be a mapping nobody could recompute, and a
mistyped id would produce a model FaVe agrees with and nothing can contradict.

The FPL inventory (`roles_and_services.txt`) is hand-written because a policy is
an intent and cannot be derived from the data. What CAN be checked is that every
role it names corresponds to a real endpoint with the address it claims, and
`test/test_cloud_fpl.py` does exactly that against this module.
"""

from __future__ import annotations

import json

from typing import Dict, List, Optional

from bench.wl_cloud.cloud_tf import NodeModel, Rule, node_name, read_match_field


#: The name the FPL inventory knows the internet by. The dataset's two internet
#: nodes are not a host pair -- the gateway is a DEVICE holding the inbound NAT
#: rules and the receive node is an ordinary sink -- so they are folded by hand
#: here rather than by the `_rx`/`_tx` rule below. `Internet` is FPL's builtin
#: role name and `reach_csv_to_checks` special-cases it, so the model-side name
#: stays lower case and the inventory maps one to the other.
INTERNET = 'internet'

#: FPL's builtin role for the outside world. The model's own endpoint for it is
#: lower case, so this is the one name that is not simply carried across.
INTERNET_ROLE = 'Internet'

_GATEWAY = 'internet_gw'
_INTERNET_RX = 'internet_rx'


class Endpoint:
    """ One thing an FPL role may name: a name, the node traffic is injected
    at, the node traffic is observed at, and the address the injector carries.

    `ipv4` is None for an endpoint whose injector is unconstrained -- only the
    internet gateway, which is a device rather than a host and so has no `/30`
    of its own.
    """

    __slots__ = ('name', 'tx', 'rx', 'ipv4')

    def __init__(self, name: str, tx: int, rx: int, ipv4: Optional[str] = None) -> None:
        self.name = name
        self.tx = tx
        self.rx = rx
        self.ipv4 = ipv4

    def __repr__(self) -> str:
        return 'Endpoint(%r, tx=%d, rx=%d, ipv4=%r)' % (
            self.name, self.tx, self.rx, self.ipv4)

    @property
    def source_device(self) -> str:
        return 'source.%s' % self.name

    @property
    def probe_device(self) -> str:
        return 'probe.%s' % self.name

    # The three below are what `cloud_preparation.build_model` reads off a role
    # member, and they are the reason it has ONE code path for both kinds. An
    # `Endpoint` is the simple case of `cloud_preparation.RoleEndpoint`: it
    # injects at one node, is observed at one node, and carries no header
    # constraint of its own because the policy addresses it by name alone.

    @property
    def inject(self) -> int:
        return self.tx

    @property
    def fields(self) -> List[str]:
        return []

    @property
    def observe(self) -> List[int]:
        return [self.rx]


def _source_address(model: NodeModel, node: int) -> Optional[str]:
    """ The `/30` a source node's own rule constrains its traffic to.

    A source has exactly one rule by construction (`NodeModel._forwards_onward`
    files anything else as a device), so there is no choice to make here.
    """
    rules: List[Rule] = model.rules_at(node)
    if len(rules) != 1:
        return None
    address = read_match_field(rules[0].match, 'packet.ipv4.source')
    return None if address is None else str(address)


def derive_endpoints(model: NodeModel) -> Dict[str, Endpoint]:
    """ Every endpoint of `model`, keyed by the name an FPL role would use.

    A host contributes one endpoint pairing its `_tx` source with its `_rx`
    sink. A half pair contributes NOTHING: a name that resolved to only one
    side would give a role either a generator with no probe or a probe with no
    generator, and every check naming it would then fail for a reason that has
    nothing to do with the network.
    """
    transmit: Dict[str, int] = {}
    receive: Dict[str, int] = {}

    for node in model.sources:
        name = node_name(node)
        if name.endswith('_tx'):
            transmit[name[:-3]] = node

    for node in model.sinks:
        name = node_name(node)
        if name.endswith('_rx'):
            receive[name[:-3]] = node

    endpoints = {}
    for name in sorted(set(transmit) & set(receive)):
        endpoints[name] = Endpoint(
            name, transmit[name], receive[name],
            ipv4=_source_address(model, transmit[name]))

    # The internet, whose two nodes the `_rx`/`_tx` rule cannot pair: the
    # gateway is a device (it holds the inbound NAT rules, so nothing but a
    # generator attached directly to it can put traffic into the network from
    # outside) and `internet_rx` is an ordinary sink.
    gateway = next(
        (n for n in model.devices if node_name(n) == _GATEWAY), None)
    sink = next(
        (n for n in model.sinks if node_name(n) == _INTERNET_RX), None)
    if gateway is not None and sink is not None:
        endpoints[INTERNET] = Endpoint(INTERNET, gateway, sink, ipv4=None)

    return endpoints


class InventoryError(Exception):
    """ The FPL inventory names something the model does not have. """


def role_members(roles_path: str,
                 endpoints: Dict[str, Endpoint]) -> Dict[str, Endpoint]:
    """ The model endpoint each FPL role stands for, keyed by role name.

    THE INVENTORY IS FABRICATED AND THIS IS WHERE THAT IS CHECKED. The dataset
    ships no roles, so `roles_and_services.txt` is hand-written -- a policy is
    an intent and cannot be derived. What CAN be verified is that every role it
    names is a real endpoint carrying the address the role claims, and both are
    refused here rather than in a test alone: a role with no endpoint would
    yield checks naming a generator that does not exist, and a role whose
    declared `ipv4` is not the one its generator actually injects would ask
    about a different host than the policy says.
    """
    roles = json.load(open(roles_path, 'r'))
    members: Dict[str, Endpoint] = {}

    for role in roles:
        name = role['name']
        key = INTERNET if name == INTERNET_ROLE else name

        endpoint = endpoints.get(key)
        if endpoint is None:
            raise InventoryError(
                "FPL role %r names no endpoint of this model. Every role must "
                "stand for a node pair the transfer function actually has "
                "(cloud_endpoints.derive_endpoints), or the checks it "
                "generates address a generator that was never built."
                % name)

        declared = role.get('attributes', {}).get('ipv4')
        if declared is not None and declared != endpoint.ipv4:
            raise InventoryError(
                "FPL role %r declares ipv4 %r, but %s injects %r. The policy "
                "would then ask about a different host than it names."
                % (name, declared, endpoint.name, endpoint.ipv4))

        members[name] = endpoint

    return members
