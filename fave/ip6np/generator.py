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

from packet_filter import PacketFilterModel
from openflow.rule import SwitchRuleField, Match, SwitchRule, Forward
from util.collections_util import dict_union
from util.packet_util import is_ip as is_ipv4
from util.packet_util import portrange_to_prefixed_bitvectors

def _is_rule(ast):
    return ast.has_child("-A") or ast.has_child("-I") or ast.has_child("-P")


def _is_state_checking_rule(rule):
    return any([
        True for f in rule.match if f.name == 'module.conntrack.ctstate' and f.value == 'ESTABLISHED'
    ])

def _is_new_state_rule(rule):
    return any([
        True for f in rule.match if f.name == 'module.conntrack.ctstate' and f.value == 'NEW'
    ])


def _has_multiports(body):
    return any([f.name in ['sports', 'dports'] for f in body])


_TAGS = {
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
    "state" : "module.conntrack.ctstate",
    "ctstate" : "module.conntrack.ctstate",
    #"tcp-flags" : "packet.upper.tcp.flags", # mask comp
    #"syn" : "packet.upper.tcp.syn",
    #"tcp-option" : "packet.upper.tcp.option", # number
    #"tos" : "packet.ipv6.priority", # value[/mask]
    "m" : "module",
    "module" : "module",
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
    "vlan" : "packet.ether.vlan",
    "svlan" : "packet.ether.svlan",
    "dvlan" : "packet.ether.dvlan"
}

def _ast_to_rule(node, ast, idx=0):
    is_default = False
    strip_ap = lambda x: x.lstrip('-')

    tag = lambda k: _TAGS[strip_ap(k)]

    is_field = lambda f: _TAGS.has_key(strip_ap(f.value))
    is_ignored = lambda f: strip_ap(f.value) in ['m', 'module', 'comment']
    is_negated = lambda f: f.is_negated()

    value = lambda f: f.get_first().value if f.get_first() is not None else ""

    if ast.has_child("-A"):
        ast = ast.get_child("-A")
    elif ast.has_child("-P"):
        ast = ast.get_child("-P")
        is_default = True

    if not ast:
        return {}

    if ast.has_child("-i"):
        tmp = ast.get_child("-i")
        if "." in value(tmp):
            iface, vlan = value(tmp).split(".")
            tmp.get_first().value = node+'.'+iface+'_ingress'
            vast = ast.add_child("svlan")
            vast.add_child(vlan)
        else:
            tmp.get_first().value = node+'.'+value(tmp)+'_ingress'
    if ast.has_child("-o"):
        tmp = ast.get_child("-o")
        if "." in value(tmp):
            iface, vlan = value(tmp).split(".")
            tmp.get_first().value = node+'.'+iface+'_egress'
            vast = ast.add_child("dvlan")
            vast.add_child(vlan)
        else:
            tmp.get_first().value = node+'.'+value(tmp)+'_egress'

    has_src = ast.has_child("-s")
    has_dst = ast.has_child("-d")
    if has_src:
        tmp = ast.get_child("-s")
        if is_ipv4(tmp.get_first().value):
            tmp.value = "s4"
    if has_dst:
        tmp = ast.get_child("-d")
        if is_ipv4(tmp.get_first().value):
            tmp.value = "d4"

    body = [
        SwitchRuleField(tag(f.value), value(f)) for f in ast if is_field(f) and not is_ignored(f)
    ]

    chain = _get_chain_from_ast(ast)

    action = _get_action_from_ast(ast)
    actions = [] if action == 'DROP' else [Forward(ports=[node+'.'+chain+'_'+action.lower()])]

    rules = {}
    multiports = []
    if ast.has_child('--sports'):
        multiports.append(
            SwitchRuleField('sports', value(ast.get_child('--sports')))
        )
    if ast.has_child('--dports'):
        multiports.append(
            SwitchRuleField('dports', value(ast.get_child('--dports')))
        )
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

        combinations = [(sport, dport) for sport in sports for dport in dports]

        if combinations:
            for i, comb in enumerate(combinations):
                sport, dport = comb
                rules[idx+i] = SwitchRule(
                    node,
                    node+'.'+chain,
                    idx+i,
                    in_ports=[node+'.'+chain+'_in'],
                    match=Match(body+[SwitchRuleField('packet.upper.sport', sport), SwitchRuleField('packet.upper.dport', dport)]),
                    actions=actions
                )

        else:
            for i, sport in enumerate(sports):
                rules[idx+i] = SwitchRule(
                    node,
                    node+'.'+chain,
                    idx+i,
                    in_ports=[node+'.'+chain+'_in'],
                    match=Match(body+[SwitchRuleField('packet.upper.sport', sport)]),
                    actions=actions
                )
            for i, dport in enumerate(dports, start=len(sports)):
                rules[idx+i] = SwitchRule(
                    node,
                    node+'.'+chain,
                    idx+i,
                    in_ports=[node+'.'+chain+'_in'],
                    match=Match(body+[SwitchRuleField('packet.upper.dport', dport)]),
                    actions=actions
                )

    else:
        rules[idx if not is_default else 65535] = SwitchRule(
            node,
            node+'.'+chain,
            idx if not is_default else 65535,
            in_ports=[node+'.'+chain+'_in'],
            match=Match(body),
            actions=actions
        )

    return { chain : rules }


def _get_rules_from_ast(node, ast, idx=0):
    if _is_rule(ast):
        return _ast_to_rule(node, ast, idx)
    elif not ast.has_children():
        return {}
    else:
        cnt = 0
        chains = {}
        for st in ast:
            rules = _get_rules_from_ast(node, st, idx+cnt+1)

            for chain, rules in rules.iteritems():
                chains.setdefault(chain, {})
                chains[chain].update(rules)
                cnt += len(rules)

        return chains


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


def _get_state_checking_rules(rules):
    return {r.idx : r for r in rules if _is_state_checking_rule(r)}


_SWAP_FIELDS={
    "packet.ipv4.source" : "packet.ipv4.destination",
    "packet.ipv4.destination" : "packet.ipv4.source",
    "packet.ipv6.source" : "packet.ipv6.destination",
    "packet.ipv6.destination" : "packet.ipv6.source",
    "packet.upper.sport" : "packet.upper.dport",
    "packet.upper.dport" : "packet.upper.sport",
    "packet.ether.source" : "packet.ether.destination",
    "packet.ether.destination" : "packet.ether.source",
    "packet.ether.svlan" : "packet.ether.dvlan",
    "packet.ether.dvlan" : "packet.ether.svlan",
    "out_port" : "in_port",
    "in_port" : "out_port"
}


def _swap_port_value_direction(field):
    if field.name == 'in_port':
        return field.value.replace('_ingress', '_egress')
    elif field.name == 'out_port':
        return field.value.replace('_egress', '_ingress')
    else:
        return field.value


def _swap_direction(field):
    value = _swap_port_value_direction(field)

    return SwitchRuleField(
        _SWAP_FIELDS.get(field.name, field.name), value
    )


def _derive_general_state_shell(rules, state_checking_rules):
    return [
        SwitchRule(
            r.node,
            r.tid,
            r.idx,
            in_ports=r.in_ports,
            match=Match([
                _swap_direction(f) for f in r.match
            ] + [
                SwitchRuleField('related', '1')
            ]),
            actions=r.actions
        ) for r in rules if r not in state_checking_rules.values()
    ]


def _get_block_intervals(state_checking_rules, rules_size):
    intervals = []
    last = 0
    cnt = 0
    for key in sorted(state_checking_rules.keys()):
        rule = state_checking_rules[key]
        intervals.append((cnt, last, rule.idx))
        last = rule.idx
        cnt += 1

    intervals.append((cnt, last, rules_size+1))

    return intervals


def _calculate_blocks(rules, intervals):
    rules_size = len(rules)
    blocks = []

    processed = 0
    for idx, start, end in intervals:
        block = []
        for rule in rules[processed:]:
            if start >= rule.idx or rule.idx >= end:
                break

            match = Match(dc(rule.match) + [
                SwitchRuleField('related', '0')
            ]) if _is_new_state_rule(rule) else dc(rule.match)

            block.append(SwitchRule(
                rule.node,
                rule.tid,
                2*idx*rules_size+rule.idx,
                in_ports=rule.in_ports,
                match=match,
                actions=rule.actions
            ))

            processed += 1

        blocks.append(block)
        processed += 1 # skip state checking rule

    return blocks


def _adjust_interfaces(match, chain):
    if chain == 'forward_filter': return match

    for field in match:
        if field.name in ['in_port', 'out_port']:
            if chain == 'input_filter':
                field.value = field.value.replace('egress', 'ingress')
            elif chain == 'output_filter':
                field.value = field.value.replace('ingress', 'egress')

    return match


def _adjust_ports(ports, chain):
    if chain == 'forward_filter': return ports
    elif chain == 'input_filter': return [p.replace('output', 'input') for p in ports]
    elif chain == 'output_filter': return [p.replace('input', 'output') for p in ports]
    else: raise Exception('cannot adjust ports for unknown chain: %s' % chain)


def _adjust_action(action, chain):
    if isinstance(action, Forward):
        action.ports = _adjust_ports(action.ports, chain)
    return action


def _derive_conditional_state_shells(
        intervals, general_state_shell, state_checking_rules, rules_size, chain
    ):
    cond_shells = []

    for idx, start, end in intervals:
        if end in state_checking_rules:
            state_checking_rule = state_checking_rules[end]
        else:
            break
        cond_shell = []

        for rule in general_state_shell:

            match = _adjust_interfaces(
                dc(rule.match.intersect(state_checking_rule.match)),
                chain
            )

            in_ports = _adjust_ports(rule.in_ports, chain)

            if not any([f.value == None for f in match]):
                actions = [
                    Forward([])
                ] if state_checking_rule.actions[0].ports == [] else [
                    _adjust_action(dc(a), chain) for a in rule.actions
                ]

                cond_shell.append(SwitchRule(
                    rule.node,
                    rule.node+'.'+chain,
                    (2*idx+1)*rules_size+rule.idx,
                    in_ports=in_ports,
                    match=match,
                    actions=actions
                ))

        cond_shells.append(cond_shell)

    return cond_shells


def _interwheave_state_shell(intervals, blocks, conditional_state_shells, chain):
    interwhoven_state_shell = []
    cnt = 0

    is_conntrack = lambda f: f.name == 'module.conntrack.ctstate' or (
        f.name == 'module' and f.value == 'conntrack'
    )

    for idx, _start, _end in intervals:
        block = blocks[idx]
        cond_shell = conditional_state_shells[idx] if idx < len(conditional_state_shells) else []

        for rule in block:
            interwhoven_state_shell.append(SwitchRule(
                rule.node,
                rule.tid,
                cnt,
                in_ports=rule.in_ports,
                match=Match([f for f in rule.match if not is_conntrack(f)]),
                actions=rule.actions
            ))
            cnt += 1

        for rule in cond_shell:
            interwhoven_state_shell.append(SwitchRule(
                rule.node,
                rule.tid,
                cnt,
                in_ports=rule.in_ports,
                match=Match([f for f in rule.match if not is_conntrack(f)]),
                actions=rule.actions
            ))
            cnt += 1

    return interwhoven_state_shell


_SWAP_CHAIN = {
    'input_filter' : 'output_filter',
    'output_filter' : 'input_filter',
    'forward_filter' : 'forward_filter',
}

def _transform_ast_to_model(ast, node, ports=None, address=None):
    model = PacketFilterModel(node, ports=ports, address=address)
    chains = _get_rules_from_ast(node, ast)

    chain_rules = {}
    chain_blocks = {}
    chain_general_shells = {}
    chain_cond_shells = {}
    chain_intervals = {}
    chain_checking_rules = {}

    for chain, rules in chains.iteritems():
        rules = [r for _i, r in sorted(rules.iteritems(), key=lambda x: x[0])]
        for idx, rule in enumerate(rules, start=1):
            rule.idx = idx
        chain_rules[chain] = rules

        state_checking_rules = _get_state_checking_rules(rules)
        chain_checking_rules[chain] = state_checking_rules

        general_state_shell = _derive_general_state_shell(
            rules,
            state_checking_rules
        )
        chain_general_shells[chain] = general_state_shell

        intervals = _get_block_intervals(state_checking_rules, len(rules))
        chain_intervals[chain] = intervals

        blocks = _calculate_blocks(rules, intervals)
        chain_blocks[chain] = blocks

    for chain in chains:
        conditional_state_shells = _derive_conditional_state_shells(
            chain_intervals[chain],
            chain_general_shells[_SWAP_CHAIN[chain]],
            chain_checking_rules[chain],
            len(chain_rules[chain]),
            chain
        )
        chain_cond_shells[chain] = conditional_state_shells



    for chain in chains:
        interwhoven_state_shell = _interwheave_state_shell(
            chain_intervals[chain],
            chain_blocks[chain],
            chain_cond_shells[chain],
            chain
        )

        for rule in interwhoven_state_shell:
            model.tables[rule.tid if rule.tid.startswith(node) else node+'.'+rule.tid].append(rule)

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
    model = _transform_ast_to_model(ast, node, ports=ports, address=address)

    return model
