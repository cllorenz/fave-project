#!/usr/bin/env python2

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

import json

from copy import copy, deepcopy

from abstract_device import AbstractDeviceModel

from rule.rule_model import Rule, Forward, Match, RuleField, Rewrite

from util.model_util import TABLE_MAX
from util.packet_util import is_ip as is_ipv4

BASE_ROUTING_EXACT=0
BASE_ROUTING_WRONG_IO=TABLE_MAX/4*1
BASE_ROUTING_WRONG_AP=TABLE_MAX/4*2
BASE_ROUTING_RULE=TABLE_MAX/4*3


class AbstractFirewallModel(AbstractDeviceModel):
    def __init__(self, node, pf_type, ports=None):
        super(AbstractFirewallModel, self).__init__(node, pf_type)

        self.ports = {
            node + '.' + str(port) : "" for port in (
                ports if ports is not None else ["1", "2"]
            )
        }


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        npf = AbstractFirewallModel(
            self.node,
            self.type,
            ports=self.ports
        )
        npf.tables = copy(self.adds)

        return npf


    def __str__(self):
        return "%s\nrules:\n\t%s\nchains:\n\t%s\nports:\n\t%s" % (
            super(AbstractFirewallModel, self).__str__(),
            str(self.chains),
            str(self.ports)
        )


    def ingress_port(self, port):
        if port in self.internal_ports:
            return port
        else:
            return port + "_ingress"


    def egress_port(self, port):
        if port in self.internal_ports:
            return port
        else:
            return port + "_egress"


    def set_address(self, address):
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
            ) for idx, port in enumerate(self.ports, start=len(self.ports)+1) if port.endswith("_ingress")
        ]


    def add_rules(self, rules):
        """ Add a rule to the post_routing chain.

        Keyword arguments:
        rule -- new rule
        """

        exact_rules = []
        wrong_io_rules = []
        normal_rules = []

        for rule in rules:
            assert isinstance(rule, Rule)

            idx = rule.idx

            rule.in_ports = [self.node+'.routing_in']

            output_ports = []
            for action in [a for a in rule.actions if isinstance(a, Forward)]:

                for port in action.ports:
                    if port.startswith(self.node) and port.endswith('_egress'):
                        pass
                    elif port.startswith(self.node):
                        port = port + '_egress'
                    else:
                        port = self.node+'.'+port+'_egress'

                    output_ports.append(port)

                action.ports = [self.node+".routing_out"]


            # first, forward traffic that already has the destination and output
            # ports set correctly (via a filtering rule set)
            rule_exact = deepcopy(rule)
            rule_exact.idx = BASE_ROUTING_EXACT + idx
            rule_exact.match.extend([RuleField("out_port", port) for port in output_ports])


            # second, drop traffic that has an incorrect destination set for an
            # output port
            rule_wrong_io = deepcopy(rule)
            rule_wrong_io.idx = BASE_ROUTING_WRONG_IO + idx
            rule_wrong_io.match.filter("packet.ipv6.destination")
            rule_wrong_io.match.extend([RuleField("out_port", port) for port in output_ports])
            rule_wrong_io.actions = []


            # third, forward traffic with the destination set
            rewrites = [Rewrite(rewrite=[RuleField("out_port", port) for port in output_ports])]
            rule.idx = BASE_ROUTING_RULE + idx
            rule.actions.extend(rewrites)

            rule_exact.tid = self.node+".routing"
            rule_wrong_io.tid = self.node+".routing"
            rule.tid = self.node+".routing"

            exact_rules.append(rule_exact)
            wrong_io_rules.append(rule_wrong_io)
            normal_rules.append(rule)

        super(AbstractFirewallModel, self).add_rules(exact_rules)
        super(AbstractFirewallModel, self).add_rules(wrong_io_rules)
        super(AbstractFirewallModel, self).add_rules(normal_rules)


    def remove_rule(self, idx):
        """ Remove a rule from the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        """
        super(AbstractFirewallModel, self).remove_rule(idx)
        del self.tables[self.node+".routing"][rule_exact.idx]
        del self.tables[self.node+".routing"][rule_wrong_io.idx]
        del self.tables[self.node+".routing"][rule.idx]


    def update_rule(self, idx, rule):
        """ Update a rule in the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule substitute
        """

        assert isinstance(rule, Rule)

        rule.idx = idx

        self.remove_rule(idx)
        self.add_rules([rule])
