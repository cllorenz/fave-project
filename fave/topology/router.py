#!/usr/bin/env python2

""" This module provides a model for routers.
"""

import json
import math

from netplumber.model import Model
from netplumber.mapping import Mapping
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from openflow.switch import SwitchRuleField, Match, Forward, SwitchRule, Rewrite

class RouterModel(Model):
    """ This class provides a model for routers.
    """

    def __init__(
            self,
            node,
            ports=None,
            acls=None,
            vlan_to_ports=None,
            routes=None,
            mapping=None,
            vlan_to_acls=None
    ):
        super(RouterModel, self).__init__(node, "router", mapping=mapping)

        ports = ports if ports is not None else {"1" : 1, "2" : 1}

        internal_ports = {
            "acl_in_out" : 1,
            "routing_in" : 2,
            "routing_out" : 3,
            "acl_out_in" : 4,
            "acl_out_out" : 5,
            "post_routing_in" : 6
        }

        plen = len(ports)
        iplen = len(internal_ports)
        input_ports = {
            "in_"+str(i) : (iplen+ports[str(i)]) \
                for i in range(1, plen/2+1)
        }

        output_ports = {
            "out_"+str(i) : (iplen+plen+ports[str(i-plen/2)]) \
                for i in range(plen/2+1, plen+1)
        }

        self.ports = dict(
            internal_ports.items() + input_ports.items() + output_ports.items()
        )

        self.wiring = [
            ("acl_in_out", "routing_in"),
            ("routing_out", "acl_out_in"),
            ("acl_out_out", "post_routing_in")
        ]

        get_name = lambda x: "%s_%s" % (node, x[0][4:])
        get_port = lambda x: x[1]
        post_routing = [
            SwitchRule(
                node, "post_routing", idx,
                match=Match(
                    fields=[SwitchRuleField("interface", get_port(port))]
                ),
                actions=[
                    Rewrite(rewrite=[SwitchRuleField("interface", "x"*32)]),
                    Forward(ports=[get_name(port)])
                ]
            ) for idx, port in enumerate(output_ports.items())
        ]

        self.tables = {
            "acl_in" : [],
            "acl_out" : [],
            "routing" : [],
            "post_routing" : post_routing,
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

        for table in ['acl_in', 'acl_out', 'routing']:
            self.tables.setdefault(table, [])

        if not self.mapping:
            self.mapping = Mapping()

        self.mapping.extend("interface")

        for vlan, in_ports in self.vlan_to_ports.items():
            vlan_match = [SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD["vlan"], vlan)]
            self.mapping.extend(OXM_FIELD_TO_MATCH_FIELD["vlan"])

            for aid, acl in enumerate(self.vlan_to_acls):
                if vlan not in self.acls:
                    continue

                acl_rules = self.acls[acl_name(acl)]

                for rid, rule in enumerate(acl_rules):
                    acl_rule, acl_action = rule
                    is_in = acl.startswith("in_")
                    acl_table = "acl_in" if is_in else "acl_out"
                    acl_port = "acl_in_out" if is_in else "acl_out_out"
                    acl_in_ports = in_ports if is_in else []

                    for field, _value in acl_rule:
                        if OXM_FIELD_TO_MATCH_FIELD[field] not in self.mapping:
                            self.mapping.extend(OXM_FIELD_TO_MATCH_FIELD[field])

                    rule = SwitchRule(
                        self.node, acl_table, aid+rid, acl_in_ports,
                        match=Match(fields=vlan_match + [
                            SwitchRuleField(
                                OXM_FIELD_TO_MATCH_FIELD[k], v
                            ) for k, v in acl_body(acl_rule)
                        ]),
                        actions=[Forward(ports=[acl_port] if acl_permit(acl_action) else [])]
                    )

                    if not rule in self.tables[acl_table]:
                        self.tables[acl_table].append(rule)


        for idx, route in enumerate(self.routes):
            rule_body, out_ports = route

            for field, _value in rule_body:
                if OXM_FIELD_TO_MATCH_FIELD[field] not in self.mapping:
                    self.mapping.extend(OXM_FIELD_TO_MATCH_FIELD[field])

            rule_body = [
                SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD[k], v) for k, v in rule_body
            ]

            for port in out_ports:
                rule = SwitchRule(
                    self.node, "routing", idx, [],
                    match=Match(fields=rule_body),
                    actions=[
                        Rewrite(rewrite=[
                            SwitchRuleField("interface", "{:032b}".format(port))
                        ]),
                        Forward(ports=["routing_out"])
                    ]
                )

                if not rule in self.tables["routing"]:
                    self.tables["routing"].append(rule)

        for rules in self.tables.values():
            for rule in rules:
                rule.calc_vector(self.mapping)


    def to_json(self):
        """ Converts router model to JSON.
        """

        self.persist()
        j = super(RouterModel, self).to_json()
        j["mapping"] = self.mapping.to_json()
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
        router.mapping = Mapping.from_json(j["mapping"]) if "mapping" in j else Mapping()
        router.tables = {t:[SwitchRule.from_json(r) for r in j["tables"][t]] for t in j["tables"]}
        router.ports = j["ports"]
        return router


    def add_rule(self, idx, rule):
        """ Add a rule to the routing table

        Keyword arguments:
        idx -- a rule index
        rule -- new rule
        """

        assert isinstance(rule, SwitchRule)

        rewrites = []
        offset = (len(self.ports)-6)/2
        for action in rule.actions:

            ports = []
            for port in action.ports:
                ports.append("out")
            action.ports = ports

            rewrites.append(Rewrite(rewrite=[SwitchRuleField("interface", port)]))

        rule.actions.extend(rewrites)

        self.tables['routing'].insert(idx, rule)


    def remove_rule(self, idx):
        """ Remove a rule from the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        """
        rule = self.chains["routing"][idx]

        del self.tables["routing"][idx]


    def update_rule(self, idx, rule):
        """ Update a rule in the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule substitute
        """

        assert isinstance(rule, SwitchRule)

        self.remove_rule(idx)
        self.add_rule(idx, rule)


def _build_cidr(address, netmask=None, proto='6'):
    if proto == '6':
        return "%s/128" % address if '/' not in address else address

    elif proto == '4':
        prefix = 32
        if netmask:
            elems = netmask.split('.')
            num_nm = 0
            for idx, elem in enumerate(elems):
                num_nm += (int(elem) << (8*(3-idx)))

            try:
                prefix = 31-int(round(math.log(num_nm, 2)))
            except ValueError:
                prefix = 32

        return "%s/%s" % (address if not address == 'any' else '0.0.0.0', prefix)

    else:
        raise "No such protocol: %s", proto


def parse_cisco_acls(acl_file):
    """ Parses a Cisco ACL file.

    Keyword arguments:
    acl_file - path to ACl file.
    """

    if not acl_file:
        return None

    acls = {}

    with open(acl_file, 'r') as aclf:
        raw = aclf.read().split('\n')

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
                raise "Unknown rule format: %s", line

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

    with open(interface_file, 'r') as inf:
        raw = inf.read().split('\n')

        vlan = None
        for line in raw:
            nline = line.lstrip(' ')
            if nline.startswith('interface'):
                _if, _label, vlan = nline.split(' ')
                vlan_to_ports.setdefault(vlan, [])
                vlan_to_acls.setdefault(vlan, [])

            # comments, descriptions and empty line
            elif nline.startswith("#") or nline.startswith("description") or nline == "":
                pass

            # XXX: fix
            elif nline.startswith('ip address'):
                _proto, _label, _daddr, _dmask = nline.split(' ')

            # XXX: fix
            elif nline.startswith('no ip address'):
                pass

            # XXX: implement
            elif nline.startswith("ip nat"):
                pass

            elif nline.startswith('ip access-group'):
                _proto, _label, acl, direction = nline.split(' ')
                vlan_to_acls[vlan].append("%s_%s" % (direction, acl))

            else:
                continue

    return vlan_to_ports, vlan_to_acls


if __name__ == '__main__':
    RACLS = parse_cisco_acls("bench/wl-ifi/acls.txt")

    RVLAN_TO_PORTS, RVLAN_TO_ACLS = parse_cisco_interfaces("bench/wl-ifi/interfaces.txt")

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
