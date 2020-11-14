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

""" This module provides functionality to generate packet filter models from
    rule set ASTs.
"""

from copy import deepcopy as dc

from ip6np_util import field_value_to_bitvector
from packet_filter import PacketFilterModel
from openflow.rule import SwitchRuleField, Match, SwitchRule, Forward
from util.collections_util import dict_union
from util.packet_util import is_ip as is_ipv4
from util.packet_util import portrange_to_prefixed_bitvectors

def _is_rule(ast):
    return ast.has_child("-A") or ast.has_child("-I") or ast.has_child("-P")


def _is_state_rule(body):
    return any([f.name == 'packet.ipv6.proto' and f.value == 'tcp' for f in body])


def _has_multiports(body):
    return any([f.name in ['sports', 'dports'] for f in body])


def _swap_src_dst(field):
    if field.startswith("packet.ipv6"):
        return field.replace(
            "source", "destination"
        ) if "source" in field else field.replace(
            "destination", "source"
        )
    elif field.startswith("packet.upper"):
        return field.replace(
            "sport", "dport"
        ) if "sport" in field else field.replace(
            "dport", "sport"
        )
    else:
        raise Exception("cannot swap source and destination for field: %s" % field)


def _build_state_rule_from_rule(body):
    return [
        (
            SwitchRuleField(
                _swap_src_dst(field.name),
                field.value
            ) if field.name in [
                "packet.ipv6.source",
                "packet.ipv6.destination",
                "packet.upper.sport",
                "packet.upper.dport"
            ] else dc(field)
        ) for field in [f for f in body if f.name != "related"]
    ]


def _get_state_chain_from_chain(chain):
    if chain.startswith("forward"):
        return chain
    elif chain.startswith("input"):
        return chain.replace("input", "output")
    elif chain.startswith("output"):
        return chain.replace("output", "input")
    else:
        raise Exception("cannot fetch state chain from chain: %s" % chain)


def _ast_to_rule(node, ast, idx=0):
    is_default = False
    tags = {
        "i" : "in_port",
        "o" : "out_port",
        "s" : "packet.ipv6.source",
        "s4" : "packet.ipv4.source",
        "source" : "packet.ipv6.source",
        "d" : "packet.ipv6.destination",
        "d4" : "packet.ipv4.destination",
        "destination" : "packet.ipv6.destination",
        "p" : "packet.ipv6.proto",
        "protocol" : "packet.ipv6.proto",
        "icmpv6-type" : "packet.ipv6.icmpv6.type", # type[/code] | typename
        "dport" : "packet.upper.dport",
        "destination-port" : "packet.upper.dport",
        "sport" : "packet.upper.sport",
        "source-port" : "packet.upper.sport",
        #"tcp-flags" : "packet.upper.tcp.flags", # mask comp
        #"syn" : "packet.upper.tcp.syn",
        #"tcp-option" : "packet.upper.tcp.option", # number
        #"tos" : "packet.ipv6.priority", # value[/mask]
        "m" : "module",
        "limit" : "module.limit",
        "header" : "module.ipv6header.header",
        "rt" : "module.rt",
        "rt-type" : "module.ipv6header.rt.type", # type
        "rt-segsleft" : "module.ipv6header.rt.segsleft", # num[:num]
        "rt-len" : "module.ipv6header.rt.len", # length
        #"rt-0-res" : "module.ipv6header.rt.0-res" # XXX maybe later
        #"rt-0-addrs" : "module.ipv6header.rt.0-addrs", # addr[, addr...] XXX maybe later
        #"rt-0-not-strict" : "module.ipv6header.rt.0-not-strict", # XXX maybe later
        "ahspi" : "module.ipv6header.ah.spi", # spi[:spi]
        "ahlen" : "module.ipv6header.ah.len", # length
        "ahres" : "module.ipv6header.ah.res",
        "dst-len" : "module.ipv6header.dst.len", # length
        #"dst-opts" : "module.ipv6header.dst.opts", # type[length][, type[length]...]
        "eui64" : "module.ipv6header.eui64",
        "fragid" : "module.ipv6header.frag.id", # id[:id]
        #"fraglen" : "module.ipv6header.frag.len", # length
        "fragres" : "module.ipv6header.frag.res",
        "fragfirst" : "module.ipv6header.frag.first",
        "fragmore" : "module.ipv6header.frag.more",
        "fraglast" : "module.ipv6header.frag.last",
        "hbh-len" : "module.ipv6header.hbh.len", # length
        #"hbh-opts" : "module.ipv6header.hbh.opts", # type[length][, type[length]...]
        "hl-eq" : "module.ipv6header.hl.eq", # value
        "hl-lt" : "module.ipv6header.hl.lt", # value
        "hl-gt" : "module.ipv6header.hl.gt", # value
        "mh-type" : "module.ipv6header.mh.type", # type[:type...]
        "vlan" : "packet.ether.vlan"
    }

    strip_ap = lambda x: x.lstrip('-')

    tag = lambda k: tags[strip_ap(k)]

    is_field = lambda f: tags.has_key(strip_ap(f.value))
    is_negated = lambda f: f.is_negated()

    value = lambda f: f.get_first().value if f.get_first() is not None else ""

    if ast.has_child("-A"):
        ast = ast.get_child("-A")
    elif ast.has_child("-P"):
        ast = ast.get_child("-P")
        is_default = True

    if not ast:
        return ([], {})

    has_iif = ast.has_child("-i")
    has_oif = ast.has_child("-o")
    if has_iif or has_oif:
        if has_iif:
            tmp = ast.get_child("-i")
            if "." in value(tmp):
                iface, vlan = value(tmp).split(".")
                tmp.get_first().value = iface
                vast = ast.add_child("vlan")
                vast.add_child(vlan)
        if has_oif:
            tmp = ast.get_child("-o")
            if "." in value(tmp):
                iface, vlan = value(tmp).split(".")
                tmp.get_first().value = iface
                vast = ast.add_child("vlan")
                vast.add_child(vlan)

    has_src = ast.has_child("-s")
    has_dst = ast.has_child("-d")
    if has_src or has_dst:
        if has_src:
            tmp = ast.get_child("-s")
            if is_ipv4(tmp.get_first().value):
                tmp.value = "s4"
        if has_dst:
            tmp = ast.get_child("-d")
            if is_ipv4(tmp.get_first().value):
                tmp.value = "d4"

    body = [
        SwitchRuleField(tag(f.value), value(f)) for f in ast if is_field(f)
    ]

    negated = [tag(f.value) for f in ast if is_field(f) and is_negated(f)]

    action = _get_action_from_ast(ast)
    actions = [] if action == 'DROP' else [Forward(ports=[action])]

    if _is_state_rule(body) and actions != []:
        body.append(SwitchRuleField("related", "0xxxxxxx"))

    chain = _get_chain_from_ast(ast)

    rules = []
    multiports = []
    if ast.has_child('--sports'): multiports.append(SwitchRuleField('sports', value(ast.get_child('--sports'))))
    if ast.has_child('--dports'): multiports.append(SwitchRuleField('dports', value(ast.get_child('--dports'))))
    if multiports:
        sports = []
        dports = []
        for ports in multiports:
            start, end = ports.value.split(':')
            prefixed_ports = portrange_to_prefixed_bitvectors(int(start), int(end))

            if ports.name == 'sports':
                sports = prefixed_ports
            else:
                dports = prefixed_ports
#            del body[ports]

        combinations = [(sport, dport) for sport in sports for dport in dports]

        if combinations:
            for i, comb in enumerate(combinations):
                sport, dport = comb
                rules.append(SwitchRule(
                    node,
                    chain,
                    (1+idx+i)*2+1,
                    in_ports=['in'],
                    match=Match(body+[SwitchRuleField('packet.upper.sport', sport), SwitchRuleField('packet.upper.dport', dport)]),
                    actions=actions
                ))

        else:
            for i, sport in enumerate(sports):
                rules.append(SwitchRule(
                    node,
                    chain,
                    (1+idx+i)*2+1,
                    in_ports=['in'],
                    match=Match(body+[SwitchRuleField('packet.upper.sport', sport)]),
                    actions=actions
                ))
            for i, dport in enumerate(dports, start=len(sports)):
                rules.append(SwitchRule(
                    node,
                    chain,
                    (1+idx+i)*2+1,
                    in_ports=['in'],
                    match=Match(body+[SwitchRuleField('packet.upper.dport', dport)]),
                    actions=actions
                ))

    else:
        rules.append(SwitchRule(
            node,
            chain,
            (1+idx)*2+1 if not is_default else 65535,
            in_ports=['in'],
            match=Match(body),
            actions=actions
        ))

    negated_rules = {r : negated for r in rules if negated}

    if (_is_state_rule(body) or is_default) and actions != []:
        state_rules = []
        for rule in rules:
            state_body = [SwitchRuleField("related", "1xxxxxxx")] + _build_state_rule_from_rule(rule.match)
            if is_default: state_body.append(SwitchRuleField("packet.ipv6.proto", "tcp"))
            state_chain = _get_state_chain_from_chain(chain)

            state_rules.append(SwitchRule(
                node,
                state_chain,
                (1+idx)*2 if not is_default else 1,
                in_ports=['in'],
                match=Match(state_body),
                actions=[Forward(ports=['accept'])]
            ))

        rules.extend(state_rules)

    #return (rules, {rule : negated}) if negated else (rules, {})
    return (rules, negated_rules)


def _get_rules_from_ast(node, ast, idx=0):
    if _is_rule(ast):
        return _ast_to_rule(node, ast, idx)
    elif not ast.has_children():
        return ([], {})
    else:
        merge = lambda l, r: (l[0]+r[0], dict_union(l[1], r[1]))
        res = ([], {})
        cnt = 0
        for st in ast:
            rules, negated = _get_rules_from_ast(node, st, idx+cnt+1)
            res = merge(res, (rules, negated))
            cnt += len(rules)

        return res


def _get_chain_from_ast(ast):
    """ Retrieves a chain from an AST.

    Keyword arguments:
    ast -- an abstract syntax tree
    """

    chain = ast.get_first().value
    return {
        "input":"input_filter",
        "output":"output_filter",
        "forward":"forward_filter"
    }[chain.lower()]


def _get_action_from_ast(ast):
    """ Retrieves an action from an AST.

    Keyword arguments:
    ast -- an abstract syntax tree
    """

    if ast.has_child("-j"):
        return ast.get_child("-j").get_first().value
    else:
        return ast.get_first().get_first().value


def _transform_ast_to_model(ast, node, ports):
    model = PacketFilterModel(node, ports=ports)
    model.rules, model.negated = _get_rules_from_ast(node, ast)

    return model


def generate(ast, node, address, ports):
    """ Generates a packet filter model from a rule set AST.

    Keyword arguments:
    ast -- an abstract syntax tree
    node -- the node's name
    address -- the node's address
    ports -- the node's physical interfaces
    """


    # transform AST to basic model
    model = _transform_ast_to_model(ast, node, ports=ports)

    model.set_address(node, address)

    # put the rules into their chains
    model.finalize()

    return model
