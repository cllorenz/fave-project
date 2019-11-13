#!/usr/bin/env python2

""" This module provides structures to store and manipulate packet filter rule
    fields, rules and packet filter models.
"""

import json

from copy import deepcopy as dc

from netplumber.vector import Vector
from netplumber.mapping import Mapping, FIELD_SIZES

from netplumber.model import Model

from openflow.switch import SwitchRule, Forward, Match, SwitchRuleField, Miss

from util.collections_util import list_sub


def expand_field(field):
    """ Expands a negated field to a set of vectors.

    Keyword argument:
    field -- a negated field to be expanded
    """

    assert isinstance(field, SwitchRuleField)

    pfield = dc(field)
    pfield.negated = False
    nfields = []
    for idx, bit in enumerate(field.value):
        if bit == '0':
            nfield = dc(pfield)
            nfield.value.vector = "x"*idx + "1" + "x"*(pfield.value.length-idx-1)
            nfields.append(nfield)
        elif bit == '1':
            nfield = dc(pfield)
            nfield.value.vector = "x"*idx + "0" + "x"*(pfield.value.length-idx-1)
            nfields.append(nfield)
        else: # 'x'
            continue

    return nfields


def expand_rule(rule, negated):
    """ Expands a rule with negated fields to a set of rules.

    Keyword arguments:
    rule -- a rule to be expanded
    """

    assert isinstance(rule, SwitchRule)

    rules = []
    for idx, field in enumerate(rule):
        if field.name in negated:
            nfields = expand_field(field)
            rules.extend(
                [SwitchRule(
                    rule.node,
                    rule.tid,
                    rule.rid,
                    rule.action,
                    dc(rule.match[:idx])+[f]+dc(rule.match[idx+1:])
                ) for f in nfields]
            )

    return rules


class PacketFilterModel(Model):
    """ This class stores packet filter models.
    """

    def __init__(self, node, ports=None, negated=None):
        super(PacketFilterModel, self).__init__(node, "packet_filter")

        ports = ports if ports is not None else [1, 2]

        self.rules = []
        self.chains = {
            "pre_routing" : [],
            "input_rules" : [],
            "input_states" : [SwitchRule(node, 0, 65535, in_ports=['in'], actions=[Miss()])],
            "output_rules" : [],
            "output_states" : [SwitchRule(node, 0, 65535, in_ports=['in'], actions=[Miss()])],
            "forward_rules" : [],
            "forward_states" : [SwitchRule(node, 0, 65535, in_ports=['in'], actions=[Miss()])],
            "post_routing" : [],
            "internals" : [],
        }
        internal_ports = {
            "pre_routing_input" : 1,
            "pre_routing_forward" : 2,
            "input_states_in" : 3,
            "input_states_accept" : 4,
            "input_states_miss" : 5,
            "input_rules_in" : 6,
            "input_rules_accept" : 7,
            "forward_states_in" : 8,
            "forward_states_accept" : 9,
            "forward_states_miss" : 10,
            "forward_rules_in" : 11,
            "forward_rules_accept" : 12,
            "output_states_in" : 13,
            "output_states_accept" : 14,
            "output_states_miss" : 15,
            "output_rules_in" : 16,
            "output_rules_accept" : 17,
            "internals_in" : 18,
            "internals_out" : 19,
            "post_routing_in" : 20,
        }
        self.private_ports = len(internal_ports)
        input_ports = {
            "in_"+str(i) : (len(internal_ports)+len(ports)+i) \
                for i in ports[:len(ports)/2]
        }
        output_ports = {
            "out_"+str(i) : (len(internal_ports)+2*len(ports)+i) \
                for i in ports[len(ports)/2:]
        }
        self.ports = dict(
            internal_ports.items() + input_ports.items() + output_ports.items()
        )
        self.wiring = [
            ("pre_routing_input", "input_states_in"), # pre routing to input states
            ("input_states_accept", "internals_in"), # input states accept to internals
            ("input_states_miss", "input_rules_in"), # input states miss to input rules
            ("input_rules_accept", "internals_in"), # input rules to internals
            ("pre_routing_forward", "forward_states_in"), # pre routing to forward states
            ("forward_states_accept", "post_routing_in"), # forward states accept to post routing
            ("forward_states_miss", "forward_rules_in"), # forward states miss to forward rules
            ("forward_rules_accept", "post_routing_in"), # forward rules accept to post routing
            ("internals_out", "output_states_in"), # internal output to output states
            ("output_states_accept", "post_routing_in"), # output states accept to post routing
            ("output_states_miss", "output_rules_in"), # output states miss to output rules
            ("output_rules_accept", "post_routing_in") # output rules accept to post routing
        ]
        self.mapping = Mapping(length=0)
        self.negated = negated if negated else {}

        self._persist()


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        pfm = super(PacketFilterModel, self).__sub__(other)
        rules = list_sub(self.rules, other.rules)

        npf = PacketFilterModel(
            pfm.node
        )
        npf.tables = pfm.tables
        npf.rules = rules
        npf.ports = pfm.ports
        npf.mapping = pfm.mapping

        return npf



    def _persist(self):

        constraint = lambda k, m: \
            k == "input_rules" and m[k] != [] or \
            k == "input_states" and constraint("input_rules", m) or \
            k == "output_rules" and m[k] != [] or \
            k == "output_states" and constraint("output_rules", m) or \
            k == "forward_rules" and m[k] != [] or \
            k == "forward_states" and constraint("forward_rules", m) or \
            k == "pre_routing" and (
                constraint("input_rules", m) and constraint("forward_rules", m)
            ) or \
            k == "post_routing" and (
                constraint("output_rules", m) or
                constraint("forward_rules", m)
            ) or \
            k == "internals_in" and constraint("input_rules", m) or \
            k == "internals_out" and constraint("output_rules", m)

        #active = [k for k in self.chains if constraint(k, self.chains)]

        #prefix = lambda x: "_".join(x.split("_")[:2])

        self.tables = {
            k:[r for r in self.chains[k]] for k in self.chains if k not in [
                "pre_routing",
                "post_routing",
                "input_states",
                "output_states",
                "forward_states"
            ] #if k in active
        }

        self.tables["pre_routing"] = [r for r in self.chains["pre_routing"]]
        self.tables["post_routing"] = [r for r in self.chains["post_routing"]]
        for table in ["input_states", "output_states", "forward_states"]:
            chain = self.chains[table]
            self.tables[table] = [
                SwitchRule(
                    self.node,
                    "%s_%s" % (self.node, table),
                    r.idx if r.idx else i,
                    in_ports=["%s_%s_in" % (self.node, table)],
                    match=Match([SwitchRuleField(f.name, f.value) for f in r.match]),
                    actions=[Forward(ports=[
                        "%s_%s_%s" % (
                            self.node,
                            table,
                            'miss' if isinstance(r.actions[0], Miss) else 'accept'
                        )
                    ])]
                ) for i, r in enumerate(chain)
            ]

        # XXX: remove
        #self.ports = {
        #    k:v for k, v in self.ports.iteritems() #if prefix(k) in active
        #}


    def to_json(self):
        """ Converts the packet filter model to JSON.
        """

        self._persist()

        return super(PacketFilterModel, self).to_json()


    def __str__(self):
        return "%s\nrules:\n\t%s\nchains:\n\t%s\nports:\n\t%s" % (
            super(PacketFilterModel, self).__str__(),
            str(self.rules),
            str(self.chains),
            str(self.ports)
        )


    def generate_vectors(self):
        """ Generates the vectors of all stored rules.
        """

        for rule in self.rules:
            assert isinstance(rule, SwitchRule)
            rule.vector = self._generate_rule_vector(rule)


    def _generate_rule_vector(self, rule):

        mapping = self.mapping

        # initialize an all wildcard vector
        vector = Vector(length=mapping.length, preset="x")

        # handle all fields of the rule
        for field in rule.match:
            size = FIELD_SIZES[field.name]

            # unknown field
            if field.name not in mapping:
                mapping.extend(field.name)
                vector.enlarge(size)

            # known field
            offset = mapping[field.name]

            if not isinstance(field.value, Vector):
                field.vectorize()

            vector[offset:offset+size] = field.value.vector

        return vector


    def expand_rules(self):
        """ Expands all negated rule fields in this model.
        """

        nrules = []
        for rule in self.rules:
            assert isinstance(rule, SwitchRule)
            if rule in self.negated:
                nrules.extend(expand_rule(rule, self.negated[rule]))
            else:
                nrules.append(rule)

        self.rules = nrules
        self.negated = {}


    def normalize(self):
        """ Normalizes model by enlarging all stored rules.
        """
        for rule in self.rules:
            assert isinstance(rule, SwitchRule)
            rule.enlarge_vector_to_length(self.mapping.length)


    # XXX: ugly hack
    def _reorder_defaults(self):
        for chain in ["input_rules", "forward_rules", "output_rules"]:
            chn = self.chains[chain]
            if not chn:
                continue

            if len(chn) >= 1:
                default = chn[0]
                chn.remove(default)
                chn.append(default)


    def finalize(self):
        """ Finalize model by fill chains and reorder defaults.
        """

        for rule in self.rules:
            assert isinstance(rule, SwitchRule)
            self.chains[rule.tid].append(rule)
        self._reorder_defaults()


    def set_address(self, node, address):
        """ Set the packet filter's address.
        """

        self.chains["pre_routing"] = [
            SwitchRule(
                node, 1, 1,
                in_ports=[p[3:] for p in self.ports if p.startswith('in_')],
                match=Match(fields=[SwitchRuleField("packet.ipv6.destination", address)]),
                actions=[Forward(["_".join([node, "pre_routing_input"])])]
            ),
            SwitchRule(
                node, 1, 2,
                in_ports=[p[3:] for p in self.ports if p.startswith('in_')],
                match=Match(),
                actions=[Forward(["_".join([node, "pre_routing_forward"])])]
            )
        ]

        self.normalize()


    def add_rule(self, idx, rule):
        """ Add a rule to the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        rule -- new rule
        """

        assert isinstance(rule, SwitchRule)

        rule.in_ports = ['in']

        offset = (len(self.ports)-19)/2
        for action in rule.actions:
            if action.name != "forward":
                continue

            ports = []
            for port in action.ports:
                labels = port.split('.')
                prefix, rno = ('_'.join(labels[:len(labels)-1]), labels[len(labels)-1])
                ports.append("%s_%s" % (prefix, int(rno)+offset))
            action.ports = ports

        self.chains["post_routing"].insert(idx, rule)
        self.tables["post_routing"].insert(idx, rule)
        self.rules.append(rule)


    def remove_rule(self, idx):
        """ Remove a rule from the post_routing chain.

        Keyword arguments:
        idx -- a rule index
        """
        rule = self.chains["post_routing"][idx]

        del self.chains["post_routing"][idx]
        del self.tables["post_routing"][idx]
        del self.rules[rule]


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
        npf.mapping = Mapping.from_json(j["mapping"])
        return npf
