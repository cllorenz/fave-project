#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" This module provides structures to store and manipulate packet filter rule
    fields, rules and packet filter models.
"""

from __future__ import annotations

from typing import Collection, Iterable, List, Optional

from copy import copy, deepcopy

from devices.abstract_device import AbstractDeviceModel

from rule.rule_model import Rule, Forward, Match, RuleField, Rewrite

from util.packet_util import is_ip as is_ipv4

# A route at index i becomes two rules of the routing table, at 2i and 2i+1;
# see `AbstractFirewallModel.add_rules`.
_ROUTING_SLOTS = 2

class AbstractFirewallModel(AbstractDeviceModel):
    """ An abstract model for firewalls that groups common characteristica.
    """
    def __init__(
            self, node: str, pf_type: str, ports: Optional[Iterable[str]] = None
    ) -> None:
        super(AbstractFirewallModel, self).__init__(node, pf_type)

        # only used for `in` checks; subclasses store a list or a dict
        self.internal_ports: Collection[str] = []
        self.ports = {
            node + '.' + str(port) : "" for port in (
                ports if ports is not None else ["1", "2"]
            )
        }


    def __sub__(self, other: "AbstractDeviceModel") -> "AbstractFirewallModel":
        assert self.node == other.node
        assert self.type == other.type

        npf = AbstractFirewallModel(
            self.node,
            self.type,
            ports=self.ports
        )
        npf.tables = copy(self._adds)

        return npf


    def ingress_port(self, port: str) -> str:
        if port in self.internal_ports:
            return port

        return port + "_ingress"


    def egress_port(self, port: str) -> str:
        if port in self.internal_ports:
            return port

        return port + "_egress"


    def set_address(self, address: str) -> None:
        """ Set the packet filter's address.
        """

        address_type = "packet.ipv4.destination" if is_ipv4(address) else "packet.ipv6.destination"
        self.tables[self.node+".pre_routing"] = [
            Rule(
                self.node, self.node+".pre_routing", idx,
                in_ports=[port],
                match=Match(fields=[RuleField(address_type, address)]),
                actions=[
                    Rewrite(rewrite=[RuleField("in_port", port)]),
                    Forward([self.node+".pre_routing_input"])
                ]
            ) for idx, port in enumerate(self.ports, start=1) if port.endswith("_ingress")
        ] + [
            Rule(
                self.node, self.node+".pre_routing", idx,
                in_ports=[port],
                match=Match(),
                actions=[
                    Rewrite(rewrite=[RuleField("in_port", port)]),
                    Forward([self.node+".pre_routing_forward"])
                ]
            ) for idx, port in enumerate(
                self.ports, start=len(self.ports)+1
            ) if port.endswith("_ingress")
        ]


    def add_rules(self, rules: Iterable["Rule"]) -> None:
        """ Add routes to the routing table.

        `-o X` in a filter chain means what netfilter means: the rule applies
        iff ROUTING sends the packet out of X (owner, 2026-10-10). The chains
        run before `routing` here, so an `-o X` rule accepts the slice of a
        flow tagged `out_port = X`, and routing must let a packet through only
        by the route its destination takes. Each route at index i becomes, in
        route order (the table is first-match):

        * 2i   -- destination in the route's prefix and `out_port` its egress:
                  forward. An untagged flow's out_port is a wildcard, so this
                  keeps exactly the slice a rewrite to the egress would make;
        * 2i+1 -- destination in the prefix: drop. Whatever else reached this
                  route -- a slice tagged for another interface -- is a packet
                  netfilter would never have matched with that `-o`.

        A route without an egress (a discard) is the drop alone. Until
        2026-10-10 each route became three rules in index BLOCKS of 16,384
        (tagged-exact, wrong-port drop, untagged rewrite): the default route,
        index 65535, overflowed its blocks so its tagged rule ran after every
        specific route's rewrite, and a shorter route's tagged rule caught
        packets a longer route owns. On wl_example, deleting pgf's
        anti-spoofing rule then let a spoofed `-o pgf.1` slice reach office
        (bench/campaigns/results_inc_dev_20261010/FINDINGS.md).

        Only `out_port` is ever MATCHED before routing (iptables/generator.py
        never rewrites it), so a tag is either absent or an `-o`.
        """

        routes: List[Rule] = []

        for rule in rules:
            assert isinstance(rule, Rule)

            idx = rule.idx

            output_ports: List[str] = []
            for action in [a for a in rule.actions if isinstance(a, Forward)]:

                for port in action.ports:
                    if port.startswith(self.node) and port.endswith('_egress'):
                        pass
                    elif port.startswith(self.node):
                        port = port + '_egress'
                    else:
                        port = self.node+'.'+port+'_egress'

                    output_ports.append(port)

            if len(output_ports) > 1:
                # One tag, one egress: a route to several ports would need a
                # keep rule per port, and none exists in the suite.
                raise ValueError(
                    "%s route %s forwards to %d ports; a packet filter route "
                    "has one egress" % (self.node, idx, len(output_ports)))

            if output_ports:
                keep = deepcopy(rule)
                keep.idx = _ROUTING_SLOTS * idx
                keep.tid = self.node+".routing"
                keep.in_ports = [self.node+'.routing_in']
                keep.match.append(RuleField("out_port", output_ports[0]))
                keep.actions = [Forward(ports=[self.node+".routing_out"])]
                routes.append(keep)

            drop = deepcopy(rule)
            drop.idx = _ROUTING_SLOTS * idx + 1
            drop.tid = self.node+".routing"
            drop.in_ports = [self.node+'.routing_in']
            drop.actions = []
            routes.append(drop)

        super(AbstractFirewallModel, self).add_rules(routes)


    def remove_rule(self, idx: int) -> None:
        """ Remove the route at index `idx` -- both of its rules. """
        table = self.node + ".routing"
        derived = {_ROUTING_SLOTS * idx, _ROUTING_SLOTS * idx + 1}
        for rule_idx in sorted(derived):
            super(AbstractFirewallModel, self).remove_rule(rule_idx)
        self.tables[table] = [r for r in self.tables.get(table, [])
                              if r.idx not in derived]


    def update_rule(self, idx: int, rule: "Rule") -> None:
        """ Update a rule in the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule substitute
        """

        assert isinstance(rule, Rule)

        rule.idx = idx

        self.remove_rule(idx)
        self.add_rules([rule])
