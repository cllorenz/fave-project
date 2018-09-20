""" This module provides functionality to generate packet filter models from
    rule set ASTs.
"""

from ip6np_util import field_value_to_bitvector

from netplumber.vector import Vector
from netplumber.mapping import FIELD_SIZES
from packet_filter import PacketFilterModel, Field, Rule
from openflow.switch import SwitchRuleField

from util.collections_util import dict_union

def _is_rule(ast):
    return ast.has_child("-A") or ast.has_child("-I") or ast.has_child("-P")


def _ast_to_rule(ast):
    tags = {
        "i" : "interface",
        "s" : "packet.ipv6.source",
        "source" : "packet.ipv6.source",
        "d" : "packet.ipv6.destination",
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
        "state" : "module.state",
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
    }

    tag = lambda k: tags[k]

    is_field = lambda f: tags.has_key(f.value)
    is_negated = lambda f: f.is_negated()

    size = lambda k: FIELD_SIZES[tag(k)]

    value = lambda k: k.get_first().value if k.get_first() is not None else ""

    if ast.has_child("-A"):
        ast = ast.get_child("-A")
    elif ast.has_child("-P"):
        ast = ast.get_child("-P")

    if not ast:
        return ([], {})

    body = [
        Field(tag(f.value), size(f.value), value(f)) for f in ast if is_field(f)
    ]

    for field in body:
        field.vector = field_value_to_bitvector(field)

    negated = [tag(f.value) for f in ast if is_field(f) and is_negated(f)]

    action = get_action_from_ast(ast)

    chain = get_chain_from_ast(ast)
    rule = Rule(chain, action, body)

    return ([rule], {rule : negated}) if negated else ([rule], {})


def _get_rules_from_ast(ast):
    if _is_rule(ast):
        return _ast_to_rule(ast)
    elif not ast.has_children():
        return ([], {})
    else:
        merge = lambda l, r: (l[0]+r[0], dict_union(l[1], r[1]))
        return reduce(
            merge, [_get_rules_from_ast(st) for st in ast]
        )


def get_chain_from_ast(ast):
    """ Retrieves a chain from an AST.

    Keyword arguments:
    ast -- an abstract syntax tree
    """

    chain = ast.get_first().value
    return {
        "input":"input_rules",
        "output":"output_rules",
        "forward":"forward_rules"
    }[chain.lower()]


def get_action_from_ast(ast):
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
    model.rules, model.negated = _get_rules_from_ast(ast)

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

    # generate vectors from rule tree
    model.generate_vectors()

    # expand negated fields
    model.expand_rules()

    # normalize vector length
    model.normalize()

    # put the rules into their chains
    model.finalize()

    return model
