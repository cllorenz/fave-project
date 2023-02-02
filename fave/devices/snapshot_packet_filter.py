#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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
from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite


def _swap_field(field):
    if 'source' in field.name:
        return field.name.replace('source', 'destination'), field.value
    elif 'destination' in field.name:
        return field.name.replace('destination', 'source'), field.value
    elif 'sport' in field.name:
        return field.name.replace('sport', 'dport'), field.value
    elif 'dport' in field.name:
        return field.name.replace('dport', 'sport'), field.value

    return field.name, field.value


def _reverse_quintuple(quintuple):
    return Match([
        RuleField(
            *_swap_field(field)
        ) for field in quintuple
    ])


class StateCommand(object):
    """ This class provides state commands for FaVe.
    """

    def __init__(self, node, command, rules):
        self.node = node
        self.type = "state_command"
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
        """ Constructs a state command from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return StateCommand(
            j["node"],
            j["command"],
            [Rule.from_json(r) for r in j["rules"]]
        )


class SnapshotPacketFilterModel(AbstractFirewallModel):
    """ This class stores packet filter models that use state snapshots instead
        of state deduction.
    """

    def __init__(self, node, ports=None, address=None):
        super(SnapshotPacketFilterModel, self).__init__(node, "snapshot_packet_filter")

        ports = ports if ports is not None else ["1", "2"]

        self.tables = {
            node + ".pre_routing" : [],
            node + ".input_state" : [],
            node + ".input_filter" : [],
            node + ".output_filter" : [],
            node + ".output_state" : [],
            node + ".forward_filter" : [],
            node + ".forward_state" : [],
            node + ".routing" : [],
            node + ".post_routing" : [],
            node + ".internals" : [],
        }

        self.internal_ports = {
            node + ".pre_routing_input" : node + ".pre_routing",
            node + ".pre_routing_forward" : node + ".pre_routing",
            node + ".input_state_in" : node + ".input_state",
            node + ".input_state_accept" : node + ".input_state",
            node + ".input_state_miss" : node + ".input_state",
            node + ".input_filter_in" : node + ".input_filter",
            node + ".input_filter_accept" : node + ".input_filter",
            node + ".forward_state_in" : node + ".forward_state",
            node + ".forward_state_accept" : node + ".forward_state",
            node + ".forward_state_miss" : node + ".forward_state",
            node + ".forward_filter_in" : node + ".forward_filter",
            node + ".forward_filter_accept" : node + ".forward_filter",
            node + ".output_state_in" : node + ".output_state",
            node + ".output_state_accept" : node + ".output_state",
            node + ".output_state_miss" : node + ".output_state",
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

        external_ports = {node + '.' + str(port) : "" for port in ports}

        plen = len(ports)

        self.ports = dict(
            list(self.internal_ports.items()) + list(input_ports.items()) +
            list(output_ports.items()) + list(external_ports.items())
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

        for state_table in [
                node+'.input_state', node+'.forward_state', node+'.output_state'
            ]:
            self.tables[state_table] = [
                Rule(
                    node, state_table, 65535,
                    match=Match([]),
                    actions=[Forward(ports=[state_table+'_miss'])]
                )
            ]

        self.wiring = [
            (node + ".pre_routing_input", node + ".input_state_in"),
            (node + ".input_state_miss", node + ".input_filter_in"),
            (node + ".input_state_accept", node + ".internals_in"),
            (node + ".input_filter_accept", node + ".internals_in"),
            (node + ".pre_routing_forward", node + ".forward_state_in"),
            (node + ".forward_state_miss", node + ".forward_filter_in"),
            (node + ".forward_state_accept", node + ".routing_in"),
            (node + ".forward_filter_accept", node + ".routing_in"),
            (node + ".internals_out", node + ".output_state_in"),
            (node + ".output_state_miss", node + ".output_filter_in"),
            (node + ".output_state_accept", node + ".routing_in"),
            (node + ".output_filter_accept", node + ".routing_in"),
            (node + ".routing_out", node + ".post_routing_in")
        ]

        if address:
            self.set_address(address)


    def add_state(self, quintuples):
        """ Adds state entries to the packet filter.

        Positional arguments:
        quintuples -- a list of quintuples that characterize the connections to
                      be added
        """
        for quintuple in quintuples:
            quintuple.idx *= 2

            reverse_quintuple = Rule(
                quintuple.node,
                quintuple.tid,
                quintuple.idx+1,
                in_ports=[quintuple.tid+'_in'],
                match=_reverse_quintuple(quintuple.match),
                actions=quintuple.actions
            )

            self.adds.setdefault(quintuple.tid, [])
            self.adds[quintuple.tid].append(quintuple)
            self.adds[reverse_quintuple.tid].append(reverse_quintuple)


    @staticmethod
    def from_json(j):
        """ Construct a packet filter model from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        npf = SnapshotPacketFilterModel(j["node"])
        npf.tables = {}
        tables = j["tables"]
        for table in tables:
            npf.tables[table] = [Rule.from_json(r) for r in tables[table]]

        npf.ports = j["ports"]
        npf.wiring = [(p1, p2) for p1, p2 in j["wiring"]]
        return npf
