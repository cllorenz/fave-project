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

from devices.abstract_firewall import AbstractFirewallModel
from rule.rule_model import Rule, Forward, Match, RuleField, Rewrite


class RelayCommand(object):
    """ This class provides state commands for FaVe.
    """

    def __init__(self, node, command, rules):
        self.node = node
        self.type = "relay_command"
        self.command = command
        self.rules = rules


    def to_json(self):
        """ Converts the state command to JSON.
        """
        return {
            "node" : self.node,
            "type" : self.type,
            "command" : self.command,
            "rules" : [r.to_json() for r in self.rules]
        }


    @staticmethod
    def from_json(j):
        """ Constructs a relay command from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return RelayCommand(
            j["node"],
            j["command"],
            [Rule.from_json(r) for r in j["rules"]]
        )



class ApplicationLayerGatewayModel(AbstractFirewallModel):
    """ This class stores packet filter models.
    """

    def __init__(self, node, ports=None, address=None):
        super(ApplicationLayerGatewayModel, self).__init__(node, "application_layer_gateway")

        ports = ports if ports is not None else ["1", "2"]

        self.tables = {
            node + ".pre_routing" : [],
            node + ".input_filter" : [],
            node + ".output_filter" : [],
            node + ".relay" : [],
            node + ".routing" : [],
            node + ".post_routing" : []
        }

        self.internal_ports = {
            node + ".pre_routing_input" : node + ".pre_routing",
            node + ".input_filter_in" : node + ".input_filter",
            node + ".input_filter_accept" : node + ".input_filter",
            node + ".relay_in" : node + ".relay",
            node + ".relay_out" : node + ".relay",
            node + ".output_filter_in" : node + ".output_filter",
            node + ".output_filter_accept" : node + ".output_filter",
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

        external_ports = {node + '.' + str(port) : "" for port in ports}

        plen = len(ports)

        self.ports = dict(
            self.internal_ports.items() + input_ports.items() +
            output_ports.items() + external_ports.items()
        )

        self.tables[node + ".post_routing"] = [ # low priority: forward packets according to
                                                # out port field set by the routing table
            Rule(
                node, "post_routing", idx,
                in_ports=[node+".post_routing_in"],
                match=Match(
                    fields=[RuleField("out_port", "%s.%s_egress" % (node, port))]
                ),
                actions=[
                    Rewrite(rewrite=[
                        RuleField("in_port", "x"*32),
                        RuleField("out_port", "x"*32)
                    ]),
                    Forward(ports=["%s.%s_egress" % (node, port)])
                ]
            ) for idx, port in enumerate(ports, start=plen)
        ] + [ # high priority: filter packets with equal input and output port
            Rule(
                node, "post_routing", idx,
                in_ports=[node+".post_routing_in"],
                match=Match(
                    fields=[
                        RuleField("in_port", "%s.%s_ingress" % (node, port)),
                        RuleField("out_port", "%s.%s_egress" % (node, port))
                    ]
                ),
                actions=[]
            ) for idx, port in enumerate(ports)
        ]

        self.wiring = [
            (node + ".pre_routing_input", node + ".input_filter_in"),
            (node + ".input_filter_accept", node + ".relay_in"),
            (node + ".relays_out", node + ".output_filter_in"),
            (node + ".output_filter_accept", node + ".routing_in"),
            (node + ".routing_out", node + ".post_routing_in")
        ]

        if address:
            self.set_address(address)


    @staticmethod
    def from_json(j):
        """ Construct a packet filter model from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        npf = ApplicationLayerGatewayModel(j["node"])
        npf.tables = {}
        tables = j["tables"]
        for table in tables:
            npf.tables[table] = [Rule.from_json(r) for r in tables[table]]

        npf.ports = j["ports"]
        npf.wiring = [(p1, p2) for p1, p2 in j["wiring"]]
        return npf


    def add_relay(self, rules):
        """ Add rules that characterize the functionality of the relay.

        Positional arguments:
        rules -- a list of rules
        """
        for rule in rules:
            rule.tid = self.node+'.relay'
            rule.in_ports = [self.node+'.relay_in']
            for action in [a for a in rule.actions if isinstance(a, Forward) and a.ports]:
                action.ports = [self.node+'.relay_out']

            self.adds.setdefault(rule.tid, [])
            self.adds[rule.tid].append(rule)
