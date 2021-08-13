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

""" This module provides a model for routers.
"""

import json
import math

from copy import copy

from abstract_device import AbstractDeviceModel
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from openflow.rule import SwitchRuleField, Match, Forward, SwitchRule, Rewrite


CAPACITY=2**16/2**12 # XXX: ugly workaround

class RouterModel(AbstractDeviceModel):
    """ This class provides a model for routers.
    """

    def __init__(
            self,
            node,
            ports=None,
            acls=None,
            vlan_to_ports=None,
            routes=None,
            vlan_to_acls=None,
            if_to_vlans=None
    ):
        super(RouterModel, self).__init__(node, "router")

        # { port_id : [vlans] }
        self.if_to_vlans = if_to_vlans if if_to_vlans else {}

        ports = ports if ports is not None else ["1", "2"]

        internal_ports = {
            node + ".pre_routing_out" : node + ".pre_routing",
            node + ".acl_in_in" : node + ".acl_in",
            node + ".acl_in_out" : node + ".acl_in",
            node + ".routing_in" : node + ".routing",
            node + ".routing_out" : node + ".routing",
            node + ".acl_out_in" : node + ".acl_out",
            node + ".acl_out_out" : node + ".acl_out",
            node + ".post_routing_in" : node + ".post_routing"
        }

        plen = len(ports)
        input_ports = {
            node + "." + str(port) + "_ingress" : node + ".pre_routing" for port in ports
        }

        output_ports = {
            node + "." + str(port) + "_egress" : node + ".post_routing" for port in ports
        }

        external_ports = {
            node + '.' + str(port) : "" for port in ports
        }

        self.ports = dict(
            internal_ports.items() + input_ports.items() + output_ports.items() + external_ports.items()
        )

        self.wiring = [
            (node+".pre_routing_out", node+".acl_in_in"),
            (node+".acl_in_out", node+".routing_in"),
            (node+".routing_out", node+".acl_out_in"),
            (node+".acl_out_out", node+".post_routing_in")
        ]

        get_iname = lambda x: "%s_%s" % (node, x[0][3:])
        get_iport = lambda x: int(x[0][3:])
        get_oname = lambda x: "%s_%s" % (node, x[0][4:])
        get_oport = lambda x: int(x[0][4:])
        get_port = lambda x: x[1]

        get_if = lambda interface, _vlans: interface
        get_vlans = lambda _interface, vlans: vlans

        pre_routing = [ # bind vlans explicitly configured to ports
            SwitchRule(
                node, node+".pre_routing", idx,
                in_ports=[node+'.'+get_if(*item)+'_ingress'],
                match=Match(),
                actions=[
                    Rewrite(rewrite=[
                        SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["vlan"], str(get_vlans(*item)[0])),
                        SwitchRuleField("in_port", node+'.'+get_if(*item)+'_ingress')
                    ]),
                    Forward(ports=["%s.pre_routing_out" % node])
                ]
            ) for idx, item in enumerate(self.if_to_vlans.iteritems()) if get_vlans(*item) != []
        ] + [ # allow all vlans on other ports
            SwitchRule(
                node, node+".pre_routing", idx,
                in_ports=[node+'.'+port+"_ingress"],
                match=Match(),
                actions=[
                    Rewrite(rewrite=[SwitchRuleField("in_port", node+'.'+port+"_ingress")]),
                    Forward(ports=["%s.pre_routing_out" % node])
                ]
            ) for idx, port in enumerate([
                port for port in ports if port not in self.if_to_vlans
            ], start=len(self.if_to_vlans))
        ]

        post_routing = [ # low priority: forward packets according to out port
                         #               field set by the routing table
            SwitchRule(
                node, node+".post_routing", idx,
                in_ports=[node+".post_routing_in"],
                match=Match(
                    fields=[SwitchRuleField("out_port", node+'.'+port+"_egress")]
                ),
                actions=[
                    Rewrite(rewrite=[
                        SwitchRuleField("in_port", "x"*32),
                        SwitchRuleField("out_port", "x"*32)
                    ]),
                    Forward(ports=[node+'.'+port+'_egress'])
                ]
            ) for idx, port in enumerate(ports, start=plen)
        ] + [ # high priority: filter packets with equal input and output port
            SwitchRule(
                node, node+".post_routing", idx,
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

        # generic drops of reserved prefixes incoming from the internet
        acl_in = [
            SwitchRule(node, node+".acl_in", 1,
                in_ports=[node+'.acl_in_in'],
                match=Match(
                    fields=[
                        SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["vlan"], "4095"),
                        SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["ipv4_src"], "192.168.0.0/16")
                    ]
                ),
                actions=[]
            ),
            SwitchRule(node, node+".acl_in", 2,
                in_ports=[node+'.acl_in_in'],
                match=Match(
                    fields=[
                        SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["vlan"], "4095"),
                        SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["ipv4_src"], "10.0.0.0/8")
                    ]
                ),
                actions=[]
            )
        ]

        self.tables = {
            node + ".pre_routing" : pre_routing,
            node + ".acl_in" : acl_in,
            node + ".routing" : [],
            node + ".acl_out" : [],
            node + ".post_routing" : post_routing
        }

        # { vlan_id : [acls] }
        self.vlan_to_acls = vlan_to_acls if vlan_to_acls is not None else {}
        # { acl_name : [ ( [acl_body], acl_action ) ] }
        self.acls = acls if acls is not None else {}
        # { vlan_id : [in_ports] }
        self.vlan_to_ports = vlan_to_ports if vlan_to_ports is not None else {}
        # [ ([rule_body], rule_action) ]
        self.routes = routes if routes is not None else []

        self.persist()


    # is idempotent
    def persist(self):
        """ Persists ACLs and routes.
        """

        acl_name = lambda x: '_'.join(x.split('_')[1:])
        acl_body = lambda x: x
        acl_permit = lambda x: x == "permit"

        for table in [self.node+'.acl_in', self.node+'.acl_out', self.node+'.routing']:
            self.tables.setdefault(table, [])

        for vlan, in_ports in self.vlan_to_ports.iteritems():
            if vlan.startswith('nat_'):
                continue

            else:
                vlan_match = [
                    SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["vlan"], vlan)
                ]

            for acl in self.vlan_to_acls[vlan]:
                aid = int(vlan)*CAPACITY # if vlan != "0" else 2**15 # XXX: ugly workaround

                acl_rules = self.acls[acl_name(acl)]

                is_in = acl.startswith("in_")
                is_out = acl.startswith("out_")

                for rid, acl_rule in enumerate(acl_rules):
                    acl_match, acl_action = acl_rule
                    acl_table = self.node+'.'+("acl_in" if is_in else "acl_out")
                    acl_out_ports = [acl_table+'_out']
                    acl_in_ports = []

                    if is_in and in_ports:
                        acl_in_ports = in_ports
                    elif is_in or is_out:
                        acl_in_ports = [acl_table+'_in']

                    rule = SwitchRule(
                        self.node, acl_table, aid+rid,
                        in_ports=acl_in_ports,
                        match=Match(fields=vlan_match + [
                            SwitchRuleField(
                                OXM_FIELD_TO_MATCH_FIELD[k], v
                            ) for k, v in acl_body(acl_match)
                        ]),
                        actions=[
                            Forward(ports=acl_out_ports if acl_permit(acl_action) else [])
                        ]
                    )

                    self.tables.setdefault(acl_table, [])
                    self.tables[acl_table].append(rule)


        for nat in [n for n in self.vlan_to_acls if n.startswith('nat_')]:
            direction, acl = self.vlan_to_acls[nat]
            _netmask, pub_ips = self.vlan_to_ports[nat]

            is_in = direction == 'inside'
            acl_table = self.node+'.'+('acl_in' if is_in else 'acl_out')
            acl_in_ports = [acl_table+'_in'] if is_in else []
            acl_out_ports = [acl_table+"_out"]

            acl_rules = self.acls[acl]

            for idx, acl_rule in enumerate(acl_rules):
                offset = len(self.tables[acl_table])
                acl_body, acl_action = acl_rule

                for pub_ip in pub_ips:
                    rule = SwitchRule(
                        self.node, acl_table, offset+idx,
                        in_ports=acl_in_ports,
                        match=Match(fields=[
                            SwitchRuleField(
                                OXM_FIELD_TO_MATCH_FIELD[k], v
                            ) for k, v in acl_body
                        ]),
                        actions=[
                            Rewrite(rewrite=[
                                SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD['ipv4_src'], pub_ip)
                            ]),
                            Forward(ports=acl_out_ports if acl_permit(acl_action) else [])
                        ]
                    )

                    self.tables.setdefault(acl_table, [])
                    self.tables[acl_table].append(rule)


        for idx, route in enumerate(self.routes):
            rule_body, out_ports = route

            rule_body = [
                SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD[k], v) for k, v in rule_body
            ]

            for port in out_ports:
                rule = SwitchRule(
                    self.node, self.node+".routing", idx, [],
                    match=Match(fields=rule_body),
                    actions=[
                        Rewrite(rewrite=[
                            SwitchRuleField("out_port", "%s_egress" % port)
                        ]),
                        Forward(ports=[self.node+".routing_out"])
                    ]
                )

                self.tables.setdefault(self.node+".routing", [])
                self.tables[self.node+".routing"].append(rule)


    def ingress_port(self, port):
        return port + "_ingress"


    def egress_port(self, port):
        return port + "_egress"


    def to_json(self, persist=False):
        """ Converts router model to JSON.
        """

        if persist:
            self.persist()
        j = super(RouterModel, self).to_json()
        j["ports"] = self.ports
        j["tables"] = {
            t:[r.to_json() for r in self.tables[t]] for t in self.tables
        }
        return j


    @staticmethod
    def from_json(j):
        """ Builds router model from JSON.
        """

        if isinstance(j, str):
            j = json.loads(j)

        router = RouterModel(j["node"])
        router.tables = {
            t:[
                SwitchRule.from_json(r) for r in j["tables"][t]
            ] for t in j["tables"]
        }
        router.ports=j["ports"]

        return router


    def add_rules(self, rules):
        """ Add a rule to the routing table

        Keyword arguments:
        idx -- a rule index
        rule -- new rule
        """

        for rule in rules:
            assert isinstance(rule, SwitchRule)

            rule.in_ports = [self.node+'.routing_in']

            actions = []
            rewrites = []
            for action in [a for a in rule.actions]:
                if isinstance(action, Forward):
                    for port in action.ports:
                        rewrites.append(
                            SwitchRuleField("out_port", port+'_egress')
                        )

                    action.ports = [self.node+".routing_out"]
                    actions.append(action)
                elif isinstance(action, Rewrite):
                    rewrites.extend(action.rewrite)

            actions.append(Rewrite(rewrite=rewrites))
            rule.actions = actions

            rule.tid = self.node+'.routing'

        super(RouterModel, self).add_rules(rules)


    def remove_rule(self, idx):
        """ Remove a rule from the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        """
        super(RouterModel, self).remove_rule(idx)
        del self.tables[self.node+".routing"][idx]


    def update_rule(self, idx, rule):
        """ Update a rule in the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule substitute
        """

        assert isinstance(rule, SwitchRule)

        self.remove_rule(idx)
        self.add_rule(idx, rule)


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        res = RouterModel(
            self.node,
            ports=self.ports
        )

        res.tables = copy(self.adds)

        return res


def _build_cidr(address, netmask=None, proto='6', inverse_netmask=False):
    if proto == '6':
        return "%s/128" % address if '/' not in address else address

    elif proto == '4':
        prefix = 32
        if netmask and netmask == '0.0.0.0':
            prefix = 0
        elif netmask:
            elems = map(int, netmask.split('.'))

            if inverse_netmask:
                elems = [255 - elem for elem in elems]

            num_nm = 0
            for idx, elem in enumerate(elems):
                num_nm += (elem << (8*(3-idx)))

            try:
                prefix = 32-int(round(math.log(num_nm, 2)))
            except ValueError:
                prefix = 32

        return "%s/%s" % (address if not address == 'any' else '0.0.0.0', prefix)

    else:
        raise Exception("No such protocol: %s" % proto)


def parse_cisco_acls(acl_file):
    """ Parses a Cisco ACL file.

    Keyword arguments:
    acl_file - path to ACl file.
    """

    if not acl_file:
        return None

    acls = {}

    with open(acl_file, 'r') as aclf:
        raw = aclf.read().splitlines()

        for line in raw:
            if not line.startswith("access-list"):
                continue

            rule = line.split(' ')

            if len(rule) == 5:
                _al, ident, action, saddr, smask = rule
                proto = 'ip'
                daddr = dmask = None
            elif len(rule) == 6:
                _al, ident, action, proto, saddr, daddr = rule
                smask = dmask = "255.255.255.255"
            elif len(rule) == 8:
                _al, ident, action, proto, saddr, smask, daddr, dmask = rule
            else:
                raise Exception("Unknown rule format: %s" % line)

            acls.setdefault(ident, [])

            proto = '4' if proto == 'ip' else '6'
            slabel = "ipv%s_src" % proto
            scidr = _build_cidr(saddr, smask, proto)

            acl_rule = ([(slabel, scidr)], action)
            if daddr:
                dlabel = "ipv%s_dst" % proto
                dcidr = _build_cidr(daddr, dmask, proto)
                acl_rule[0].append((dlabel, dcidr))

            acls[ident].append(acl_rule)

    return acls


def parse_cisco_interfaces(interface_file):
    """ Parses a Cisco interface file.

    Keyword arguments:
    interface_file - a path to an interface file.
    """
    vlan_to_ports = {}
    vlan_to_acls = {}
    vlan_to_ips = {}
    vlan_to_domain = {}
    if_to_vlans = {}

    with open(interface_file, 'r') as inf:
        raw = inf.read().splitlines()

        vlan = None
        interface = None
        for line in raw:
            nline = line.lstrip(' ')

            if nline.startswith('interface'):
                tokens = nline.split(' ')

                if len(tokens) == 3:
                    _if, _label, vlan = tokens
                    vlan_to_ports.setdefault(vlan, [])
                    vlan_to_acls.setdefault(vlan, [])

                elif len(tokens) == 2:
                    _if, interface = tokens
                    if_to_vlans.setdefault(interface, [])

            # comments, descriptions and empty line
            elif nline.startswith("#") or nline == "":
                pass

            elif nline.startswith("description"):
                _desc, domain = nline.split(' ')
                vlan_to_domain[vlan] = domain

            elif nline.startswith('ip address'):
                _proto, _label, daddr, dmask = nline.split(' ')
                vlan_to_ips[vlan] = _build_cidr(daddr, dmask, '4', inverse_netmask=True) #XXX: not protocol agnostic

            elif nline.startswith('no ip address'):
                vlan_to_ips[vlan] = None

            elif nline.startswith("ip nat pool"):
                _proto, _nat, _pool, ident, ext_ip1, ext_ip2, _label, netmask = nline.split(' ')
                vlan_to_ports.setdefault('nat_'+ident, (netmask, [ext_ip1, ext_ip2]))

            elif nline.startswith("ip nat inside"):
                _proto, _nat, _inside, _source, _list, acl, _pool, ident = nline.split(' ')
                vlan_to_acls.setdefault('nat_'+ident, ('inside', acl))

            elif nline.startswith('ip access-group'):
                _proto, _label, acl, direction = nline.split(' ')
                vlan_to_acls[vlan].append("%s_%s" % (direction, acl))

            elif nline.startswith("switchport"):
                tokens = nline.split(' ')
                if len(tokens) < 3:
                    continue
                elif tokens[1] == 'access':
                    _sp, _ac, _vl, vlan = tokens
                    if_to_vlans[interface].append(int(vlan))

                elif tokens[1] == 'mode' and tokens[2] == 'trunk':
                    continue

                elif tokens[1] == 'trunk' and tokens[2] == 'encapsulation':
                    continue

                elif tokens[1] == 'trunk':
                    _sp, _tr, _al, _vl, vlans = tokens
                    vlans = map(int, vlans.split(','))
                    if_to_vlans[interface].extend(vlans)

            else:
                continue

    return vlan_to_domain, vlan_to_ports, vlan_to_ips, vlan_to_acls, if_to_vlans


if __name__ == '__main__':
    RACLS = parse_cisco_acls("bench/wl_ifi/acls.txt")

    _RVTD, RVLAN_TO_PORTS, _RVTI, RVLAN_TO_ACLS = parse_cisco_interfaces("bench/wl_ifi/interfaces.txt")

    RPORTS = {str(p):p for p in range(1, 17)}
    for RVLAN, RVPORTS in RVLAN_TO_PORTS.items():
        if not RVPORTS:
            RVLAN_TO_PORTS[RVLAN] = RPORTS.values()

    R3 = RouterModel(
        "bar",
        ports=RPORTS,
        acls=RACLS,
        routes=[],
        vlan_to_ports=RVLAN_TO_PORTS,
        vlan_to_acls=RVLAN_TO_ACLS
    )

    print R3.to_json()

    R4 = RouterModel.from_json(R3.to_json())

    assert R3 == R4
