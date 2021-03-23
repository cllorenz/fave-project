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

from copy import deepcopy

from netplumber.model import Model

from openflow.rule import SwitchRule, Forward, Match, SwitchRuleField, Miss, Rewrite

from util.collections_util import list_sub
from util.packet_util import is_ip as is_ipv4

BASE_ROUTING_EXACT=0
BASE_ROUTING_WRONG_IO=65535/4*1
BASE_ROUTING_WRONG_AP=65535/4*2
BASE_ROUTING_RULE=65535/4*3


class PacketFilterModel(Model):
    """ This class stores packet filter models.
    """

    def __init__(self, node, ports=None, address=None):
        super(PacketFilterModel, self).__init__(node, "packet_filter")

        ports = ports if ports is not None else ["1", "2"]

        self.tables = {
            node + ".pre_routing" : [],
            node + ".input_filter" : [],
            node + ".output_filter" : [],
            node + ".forward_filter" : [],
            node + ".routing" : [],
            node + ".post_routing" : [],
            node + ".internals" : [],
        }

        self.internal_ports = {
            node + ".pre_routing_input" : node + ".pre_routing",
            node + ".pre_routing_forward" : node + ".pre_routing",
            node + ".input_filter_in" : node + ".input_filter",
            node + ".input_filter_accept" : node + ".input_filter",
            node + ".forward_filter_in" : node + ".forward_filter",
            node + ".forward_filter_accept" : node + ".forward_filter",
            node + ".output_filter_in" : node + ".output_filter",
            node + ".output_filter_accept" : node + ".output_filter",
            node + ".internals_in" : node + ".internals",
            node + ".internals_out" : node + ".internals",
            node + ".post_routing_in" : node + ".post_routing",
            node + ".routing_in" : node + ".routing",
            node + ".routing_out" : node + ".routing"
        }

        input_ports = {
            node + "." + str(port) + "_ingress" : node + ".pre_routing" for port in ports
        }
        output_ports = {
            node + "." + str(port) + "_egress" : node + ".post_routing" for port in ports
        }

        external_ports = { node + '.' + str(port) : "" for port in ports }

        plen = len(ports)

        self.ports = dict(
            self.internal_ports.items() + input_ports.items() + output_ports.items() + external_ports.items()
        )

        self.tables[node + ".post_routing"] = [ # low priority: forward packets according to out port
                                                # field set by the routing table
            SwitchRule(
                node, "post_routing", idx,
                in_ports=[node+".post_routing_in"],
                match=Match(
                    fields=[SwitchRuleField("out_port", "%s.%s_egress" % (node, port))]
                ),
                actions=[
                    Rewrite(rewrite=[
                        SwitchRuleField("in_port", "x"*32),
                        SwitchRuleField("out_port", "x"*32)
                    ]),
                    Forward(ports=["%s.%s_egress" % (node, port)])
                ]
            ) for idx, port in enumerate(ports, start=plen)
        ] + [ # high priority: filter packets with equal input and output port
            SwitchRule(
                node, "post_routing", idx,
                in_ports=[node+".post_routing_in"],
                match=Match(
                    fields=[
                        SwitchRuleField("in_port", "%s.%s_ingress" % (node, port)),
                        SwitchRuleField("out_port", "%s.%s_egress" % (node, port))
                    ]
                ),
                actions=[]
            ) for idx, port in enumerate(ports)
        ]

        self.wiring = [
            (node + ".pre_routing_input", node + ".input_filter_in"), # pre routing to input filter
            (node + ".input_filter_accept", node + ".internals_in"), # input filter accept to internals
            (node + ".pre_routing_forward", node + ".forward_filter_in"), # pre routing to forward filter
            (node + ".forward_filter_accept", node + ".routing_in"), # forward filter accept to routing
            (node + ".internals_out", node + ".output_filter_in"), # internal output to output filter
            (node + ".output_filter_accept", node + ".routing_in"), # output filter accept to routing
            (node + ".routing_out", node + ".post_routing_in") # routing to post routing
        ]

        if address:
            self.set_address(address)


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        pfm = super(PacketFilterModel, self).__sub__(other)

        npf = PacketFilterModel(
            pfm.node
        )
        npf.tables = pfm.tables
        npf.ports = pfm.ports
        npf.wiring = pfm.wiring

        return npf


    def __str__(self):
        return "%s\nrules:\n\t%s\nchains:\n\t%s\nports:\n\t%s" % (
            super(PacketFilterModel, self).__str__(),
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
            SwitchRule(
                self.node, self.node+".pre_routing", idx,
                in_ports=[port],
                match=Match(fields=[SwitchRuleField(address_type, address)]),
                actions=[
                    Rewrite(rewrite=[SwitchRuleField("in_port", port)]),
                    Forward([self.node+".pre_routing_input"])
                ]
            ) for idx, port in enumerate(self.ports, start=1) if port.endswith("_ingress")
        ] + [
            SwitchRule(
                self.node, self.node+".pre_routing", idx,
                in_ports=[port],
                match=Match(),
                actions=[
                    Rewrite(rewrite=[SwitchRuleField("in_port", port)]),
                    Forward([self.node+".pre_routing_forward"])
                ]
            ) for idx, port in enumerate(self.ports, start=len(self.ports)+1) if port.endswith("_ingress")
        ]


    def add_rule(self, idx, rule):
        """ Add a rule to the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- new rule
        """

        assert isinstance(rule, SwitchRule)

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
        rule_exact.match.extend([SwitchRuleField("out_port", port) for port in output_ports])


        # second, drop traffic that has an incorrect destination set for an
        # output port
        rule_wrong_io = deepcopy(rule)
        rule_wrong_io.idx = BASE_ROUTING_WRONG_IO + idx
        rule_wrong_io.match.filter("packet.ipv6.destination")
        rule_wrong_io.match.extend([SwitchRuleField("out_port", port) for port in output_ports])
        rule_wrong_io.actions = []


        # third, forward traffic with the destination set
        rewrites = [Rewrite(rewrite=[SwitchRuleField("out_port", port) for port in output_ports])]
        rule.idx = BASE_ROUTING_RULE + idx
        rule.actions.extend(rewrites)

        rule_exact.tid = self.node+".routing"
        rule_wrong_io.tid = self.node+".routing"
        rule.tid = self.node+".routing"

        super(PacketFilterModel, self).add_rule(rule_exact)
        super(PacketFilterModel, self).add_rule(rule_wrong_io)
        super(PacketFilterModel, self).add_rule(rule)

        self.tables[self.node+".routing"].insert(rule_exact.idx, rule_exact)
        self.tables[self.node+".routing"].insert(rule_wrong_io.idx, rule_wrong_io)
        self.tables[self.node+".routing"].insert(rule.idx, rule)


    def remove_rule(self, idx):
        """ Remove a rule from the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        """
        super(SwitchModel, self).remove_rule(idx)
        del self.tables[self.node+".routing"][rule_exact.idx]
        del self.tables[self.node+".routing"][rule_wrong_io.idx]
        del self.tables[self.node+".routing"][rule.idx]


    def update_rule(self, idx, rule):
        """ Update a rule in the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule substitute
        """

        assert isinstance(rule, SwitchRule)


        self.remove_rule(idx)
        self.add_rule(idx, rule)


    @staticmethod
    def from_json(j):
        """ Construct a packet filter model from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        npf = PacketFilterModel(j["node"])
        npf.tables = {}
        tables = j["tables"]
        for table in tables:
            npf.tables[table] = [SwitchRule.from_json(r) for r in tables[table]]

        npf.ports = j["ports"]
        npf.wiring = [(p1, p2) for p1, p2 in j["wiring"]]
        return npf
