#!/usr/bin/env python2

from copy import deepcopy as dc

from netplumber.vector import Vector
from netplumber.mapping import Mapping,field_sizes

from netplumber.model import Model

from openflow.switch import SwitchRule,Forward,Match,SwitchRuleField


class Field(object):
    def __init__(self,name,size,value,negated=False):
        self.name = name
        self.size = size
        self.value = value
        self.vector = None
        self.negated = negated

    def __str__(self):
        return "name: %s, size: %i, value: %s, negated: %s,\n%s" % (
            self.name,
            self.size,
            self.value,
            str(self.negated),
            self.vector if self.vector else "no vector"
        )


class Rule(list):
    def __init__(self,chain,action,fields=[]):
        super(Rule,self).__init__(fields)
        self.action = action
        self.vector = Vector(0)
        self.chain = chain

    def enlarge_vector_to_length(self,length):
        self.vector.enlarge(length - self.vector.length)

    def __str__(self):
        return "fields:\n\t%s\naction: %s\nvector:\n\t%s" % (
            super(list,self).__str__(),
            self.action,
            str(self.vector)
        )


class PacketFilterModel(Model):
    def __init__(self,node,ports=[1,2]):
        super(PacketFilterModel,self).__init__(node,"packet_filter")

        self.rules = []
        self.chains = {
            "pre_routing"   : [],
            "input_rules"   : [],
            "input_states"  : [Rule("input_states",'MISS',[])],
            "output_rules"  : [],
            "output_states" : [Rule("output_states",'MISS',[])],
            "forward_rules" : [],
            "forward_states" : [Rule("forward_states",'MISS',[])],
            "post_routing"  : [],
        }
        internal_ports = {
            "pre_routing_input"     : 1,
            "pre_routing_forward"   : 2,
            "input_states_in"       : 3,
            "input_states_accept"   : 4,
            "input_states_miss"     : 5,
            "input_rules_in"        : 6,
            "input_rules_accept"    : 7,
            "forward_states_in"     : 8,
            "forward_states_accept" : 9,
            "forward_states_miss"   : 10,
            "forward_rules_in"      : 11,
            "forward_rules_accept"  : 12,
            "output_states_accept"  : 13,
            "output_states_miss"    : 14,
            "output_rules_in"       : 15,
            "output_rules_accept"   : 16,
            "internals_in"          : 17,
            "internals_out"         : 18,
            "post_routing_in"       : 19,
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
            ("pre_routing_input","input_states_in"), # pre routing to input states
            ("input_states_accept","internals_in"), # input states accept to internals
            ("input_states_miss","input_rules_in"), # input states miss to input rules
            ("input_rules_accept","internals_in"), # input rules to internals
            ("pre_routing_forward","forward_states_in"), # pre routing to forward states
            ("forward_states_accept","post_routing_in"), # forward states accept to post routing
            ("forward_states_miss","forward_rules_in"), # forward states miss to forward rules
            ("forward_rules_accept","post_routing_in"), # forward rules accept to post routing
            ("internals_out","output_states_in"), # internal output to output states
            ("output_states_accept","post_routing_in"), # output states accept to post routing
            ("output_states_miss","output_rules_in"), # output states miss to output rules
            ("output_rules_accept","post_routing_in") # output rules accept to post routing
        ]
        self.mapping = Mapping(length=0)


    def to_json(self):
        constraint = lambda k,m: \
            k == "input_rules" and m[k] != [] or \
            k == "input_states" and constraint("input_rules",m) or \
            k == "output_rules" and m[k] != [] or \
            k == "output_states" and constraint("output_rules",m) or \
            k == "forward_rules" and m[k] != [] or \
            k == "forward_states" and constraint("forward_rules",m) or \
            k == "pre_routing" and (
                constraint("input_rules",m) and constraint("forward_rules",m)
            ) or \
            k == "post_routing" and (
                constraint("output_rules",m) or
                constraint("forward_rules",m)
            ) or \
            k == "internals_in" and constraint("input_rules") or \
            k == "internals_out" and constraint("output_rules")

        active = [k for k in self.chains if constraint(k,self.chains)]

        prefix = lambda x: "_".join(x.split("_")[:2])

        chain_to_json = lambda k: \
            [(i if r.action != 'MISS' else 65535,r.vector.vector,r.action) \
                for i,r in enumerate(self.chains[k])
            ]

        self.tables = {
            k:chain_to_json(k) for k in self.chains if k != "pre_routing" #if k in active
        }
        self.tables["pre_routing"] = []

        self.ports = {
            k:v for k,v in self.ports.iteritems() #if prefix(k) in active
        }

        return super(PacketFilterModel,self).to_json()


    def __str__(self):
        return "%s\nrules:\n\t%s\nchains:\n\t%s\nports:\n\t%s" % (
            super(PacketFilterModel,self).__str__(),
            str(self.rules),
            str(self.chains),
            str(self.ports)
        )


    def generate_vectors(self):
        for rule in self.rules:
            rule.vector = self.generate_rule_vector(rule)


    def generate_rule_vector(self,rule):
        mapping = self.mapping

        # initialize an all wildcard vector
        vector = Vector(length=mapping.length,preset="x")

        # handle all fields of the rule
        for field in rule:
            # unknown field
            if field.name not in mapping:
                offset = len(vector)
                mapping[field.name] = offset
                mapping.length += field.size
                vector.enlarge(field.size)
                vector[offset:offset+field.size] = field.vector.vector

            # known field
            else:
                offset = mapping[field.name]
                vector[offset:offset+field.size] = field.vector.vector

        return vector

    def expand_rules(self):
        nrules = []
        for rule in self.rules:
            erule = self.expand_rule(rule)
            if type(erule) != list:
                nrules.append(erule)
            else:
                nrules.extend(erule)

        self.rules = nrules


    def expand_rule(self,rule):
        if any(map(lambda x: x.negated, rule)):
            rules = []
            for idx,field in enumerate(rule):
                if field.negated:
                    fields = self.expand_field(field)
                    rules.extend(
                        [Rule(
                            rule.chain,
                            rule.action,
                            dc(rule[:idx])+[f]+dc(rule[idx+1:])
                        ) for f in field]
                    )
            return rules
        else:
            return rule


    def expand_field(self,field):
        pfield = dc(field)
        pfield.negated = False
        nfields = []
        for idx,bit in enumerate(field.vector.vector):
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


    def normalize(self):
        for rule in self.rules:
            rule.enlarge_vector_to_length(self.mapping.length)


    def finalize(self):
        for rule in self.rules:
            self.chains[rule.chain].append(rule)

    def set_address(self,node,address):
        self.chains["pre_routing"] = [
            SwitchRule(
                node,1,1,
                match=Match(fields=[SwitchRuleField("packet.ipv6.destination",address)]),
                actions=[Forward(["_".join([node,"pre_routing_input"])])]
            ),
            SwitchRule(
                node,1,2,
                match=Match(),
                actions=[Forward(["_".join([node,"pre_routing_forward"])])]
            )
        ]

    def add_rule(self,idx,rule):
        self.chains["post_routing"].insert(idx,rule)

    def remove_rule(self,idx):
        del self.chains["post_routing"][idx]

    def update_rule(self,idx,rule):
        self.remove_rule(idx)
        self.add_rule(idx,rule)

    @staticmethod
    def from_json(j):
        pf = PacketFilterModel(j["node"])
        pf.tables=j["tables"]
        pf.ports=j["ports"]
        pf.wiring=[(p1,p2) for p1,p2 in j["wiring"]]
        pf.mapping=Mapping.from_json(j["mapping"])
        return pf
