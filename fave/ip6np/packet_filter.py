#!/usr/bin/env python2

""" This module provides structures to store and manipulate packet filter rule
    fields, rules and packet filter models.
"""

import json

from copy import deepcopy as dc

from netplumber.vector import Vector
from netplumber.mapping import Mapping, FIELD_SIZES

from netplumber.model import Model

from openflow.switch import SwitchRule, Forward, Match, SwitchRuleField

from util.collections_util import list_sub

from ip6np_util import field_value_to_bitvector

def expand_field(field):
    """ Expands a negated field to a set of vectors.

    Keyword argument:
    field -- a negated field to be expanded
    """

    assert isinstance(field, Field)

    pfield = dc(field)
    pfield.negated = False
    nfields = []
    for idx, bit in enumerate(field.vector.vector):
        if bit == '0':
            nfield = dc(pfield)
            nfield.vector.vector = "x"*idx + "1" + "x"*(pfield.vector.length-idx-1)
            nfields.append(nfield)
        elif bit == '1':
            nfield = dc(pfield)
            nfield.vector.vector = "x"*idx + "0" + "x"*(pfield.vector.length-idx-1)
            nfields.append(nfield)
        else: # 'x'
            continue

    return nfields


def expand_rule(rule):
    """ Expands a rule with negated fields to a set of rules.

    Keyword arguments:
    rule -- a rule to be expanded
    """

    assert isinstance(rule, Rule)

    if any([x.negated for x in rule]):
        rules = []
        for idx, field in enumerate(rule):
            if field.negated:
                fields = expand_field(field)
                rules.extend(
                    [Rule(
                        rule.chain,
                        rule.action,
                        dc(rule[:idx])+[f]+dc(rule[idx+1:])
                    ) for f in fields]
                )
        return rules
    else:
        return rule


# TODO: replace with SwitchRuleField
class Field(object):
    """ This class stores a packet filter rule field.
    """

    def __init__(self, name, size, value, negated=False):
        self.name = name
        self.size = size
        self.value = value
        self.vector = None
        self.negated = negated


    def __str__(self):
        return "name: %s, size: %i, value: %s, negated: %s, \n%s" % (
            self.name,
            self.size,
            self.value,
            str(self.negated),
            self.vector if self.vector else "no vector"
        )


    def unleash(self):
        return self.name, self.size, self.value


    def to_json(self):
        return {
            "name" : self.name,
            "size" : self.size,
            "value" : self.value,
            "vector" : self.vector.vector if self.vector else None,
            "negated" : self.negated
        }

    @staticmethod
    def from_json(j):
        if isinstance(j, str):
            j = json.loads(j)

        return Field(j["name"], j["size"], j["value"], negated=j["negated"])


# TODO: replace with SwitchRule
class Rule(list):
    """ This class stores packet filter rules.
    """

    def __init__(self, chain, action, fields=None):
        super(Rule, self).__init__(fields if fields else [])
        self.action = action
        self.vector = Vector(0)
        self.chain = chain


    def enlarge(self, length):
        self.enlarge_vector_to_length(length)


    def enlarge_vector_to_length(self, length):
        """ Enlarges the rule's vector to a certain length.

        Keyword arguments:
        length -- the target length
        """
        self.vector.enlarge(length - self.vector.length)


    def calc_vector(self, mapping):
        self.vector.enlarge(mapping.length)
        for field in self:
            offset = mapping[field.name]
            self.vector[offset:offset+field.size] = field_value_to_bitvector(field).vector


    def __str__(self):
        return "fields:\n\t%s\naction: %s\nvector:\n\t%s" % (
            super(Rule, self).__str__(),
            self.action,
            str(self.vector)
        )

    def to_json(self):
        return {
            "chain" : self.chain,
            "action" : self.action,
            "vector" : self.vector.vector,
            "fields" : [field.to_json() for field in self]
        }

    @staticmethod
    def from_json(j):
        if isinstance(j, str):
            j = json.loads(j)

        rule = Rule(
            j["chain"],
            j["action"],
            fields=[Field.from_json(field) for field in j["fields"]]
        )
        return rule


class PacketFilterModel(Model):
    """ This class stores packet filter models.
    """

    def __init__(self, node, ports=None):
        super(PacketFilterModel, self).__init__(node, "packet_filter")

        ports = ports if ports is not None else [1, 2]

        self.rules = []
        self.chains = {
            "pre_routing" : [],
            "input_rules" : [],
            "input_states" : [Rule("input_states", 'MISS')],
            "output_rules" : [],
            "output_states" : [Rule("output_states", 'MISS')],
            "forward_rules" : [],
            "forward_states" : [Rule("forward_states", 'MISS')],
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


    def to_json(self):
        """ Converts the packet filter model to JSON.
        """

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

        #chain_to_json = lambda k: \
        #    [(i if r.action != 'MISS' else 65535, r.vector.vector, r.action) \
        #        for i, r in enumerate(self.chains[k])
        #    ]

        self.tables = {
            k:[r.to_json() for r in self.chains[k]] for k in self.chains if k not in [
                "pre_routing",
                "post_routing",
                "input_states",
                "output_states",
                "forward_states"
            ] #if k in active
        }
        self.tables["pre_routing"] = [
            r.to_json() for r in self.chains["pre_routing"]
        ]
        self.tables["post_routing"] = [
            r.to_json() for r in self.chains["post_routing"]
        ]
        for table in ["input_states", "output_states", "forward_states"]:
            self.tables[table] = [
                SwitchRule(
                    self.node,
                    "%s_%s" % (self.node, table),
                    i if r.action != 'MISS' else 65535,
                    Match([SwitchRuleField(f.name, f.value) for f in r]),
                    [Forward(ports=[
                        "%s_%s_%s" % (
                            self.node,
                            table,
                            'accept' if r.action != 'MISS' else 'miss'
                        )
                    ])]
                ).to_json() for i, r in enumerate(self.chains[table])
            ]

        self.ports = {
            k:v for k, v in self.ports.iteritems() #if prefix(k) in active
        }

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
            assert isinstance(rule, Rule)
            rule.vector = self._generate_rule_vector(rule)


    def _generate_rule_vector(self, rule):

        mapping = self.mapping

        # initialize an all wildcard vector
        vector = Vector(length=mapping.length, preset="x")

        # handle all fields of the rule
        for field in rule:
            # unknown field
            if field.name not in mapping:
                mapping.extend(field.name)
                vector.enlarge(FIELD_SIZES[field.name])

            # known field
            offset = mapping[field.name]
            vector[offset:offset+field.size] = field.vector.vector

        return vector


    def expand_rules(self):
        """ Expands all rules in this model to a common length.
        """

        nrules = []
        for rule in self.rules:
            assert isinstance(rule, Rule)
            erule = expand_rule(rule)
            if isinstance(erule, Rule):
                nrules.append(erule)
            else:
                nrules.extend(erule)

        self.rules = nrules


    def normalize(self):
        """ Normalizes model by enlarging all stored rules.
        """
        for rule in self.rules:
            assert isinstance(rule, Rule)
            rule.enlarge_vector_to_length(self.mapping.length)


    # XXX: ugly hack
    def _reorder_defaults(self):
        for chain in ["input_rules", "forward_rules", "output_rules"]:
            chn = self.chains[chain]
            if not chn:
                continue

            if not chn[0]:
                default = chn[0]
                chn.remove(default)
                chn.append(default)

    def finalize(self):
        """ Finalize model by fill chains and reorder defaults.
        """

        for rule in self.rules:
            assert isinstance(rule, Rule)
            self.chains[rule.chain].append(rule)
        self._reorder_defaults()


    def set_address(self, node, address):
        """ Set the packet filter's address.
        """

        self.chains["pre_routing"] = [
            SwitchRule(
                node, 1, 1,
                match=Match(fields=[SwitchRuleField("packet.ipv6.destination", address)]),
                actions=[Forward(["_".join([node, "pre_routing_input"])])]
            ),
            SwitchRule(
                node, 1, 2,
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
            if table in [
                "pre_routing",
                "post_routing",
                "input_states",
                "output_states",
                "forward_states"
            ]:
                npf.tables[table] = [SwitchRule.from_json(r) for r in tables[table]]
            else:
                npf.tables[table] = [Rule.from_json(r) for r in tables[table]]

        npf.ports = j["ports"]
        npf.wiring = [(p1, p2) for p1, p2 in j["wiring"]]
        npf.mapping = Mapping.from_json(j["mapping"])
        return npf
