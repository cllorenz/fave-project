""" This module provides functionality to generate packet filter models from
    rule set ASTs.
"""

from util.packet_util import normalize_ipv6_address, normalize_upper_port
from util.packet_util import normalize_ipv6_proto, normalize_ipv6header_header
from netplumber.vector import Vector
from netplumber.mapping import FIELD_SIZES
from packet_filter import PacketFilterModel, Field, Rule
from openflow.switch import SwitchRuleField


def _is_rule(ast):
    return ast.has_child("-A") or ast.has_child("-I") or ast.has_child("-P")


def _normalize_interface(interface):
    if interface == "lo": # XXX: deprecated... no lo in rule set allowed
        return "0000000000000000"
    else:
        return '{:016b}'.format(int(interface))


def _normalize_module(module):
    return {
        "ipv6header" : "00000001",
        "limit" : "00000010",
        "state" : "00000011",
        "rt" : "00000100",
        "ah" : "00000101",
        "dst" : "00000110",
        "eui64" : "00000111",
        "frag" : "00001000",
        "hbh" : "00001001",
        "hl" : "00001010",
        "icmpv6" : "00001011",
        "mh" : "00001100",
        "tos" : "00001101"
    }[module]


def _normalize_limit(limit):
    # fields have the format value/unit
    val, unit = limit.split("/")
    factor = {
        None : 3600,
        "sec" : 1,
        "min" : 60,
        "hour" : 3600,
        "day" : 86400
    }[unit]
    return "{0:032b}".format(int(val) * factor)


def _normalize_states(states):
    states = states.split(",") if "," in states.value else [states]
    to_bit = lambda x: {"NEW":1, "RELATED":2, "ESTABLISHED":4, "INVALID":8}[x]
    bitmap = reduce(lambda x, y: x|y, [to_bit(x) for x in states])
    return "{0:08b}".format(bitmap)


def _normalize_icmpv6_type(icmpv6_type):
    return {
        "destination-unreachable" : "00000001xxxxxxxx",
        "packet-too-big" : "00000010xxxxxxxx",
        "time-exceeded" : "00000011xxxxxxxx",
        "parameter-problem" : "00000100xxxxxxxx",
        "echo-request" : "10000000xxxxxxxx",
        "echo-reply" : "10000001xxxxxxxx",
        "neighbour-solicitation" : "10000111xxxxxxxx",
        "neighbour-advertisement" : "10001000xxxxxxxx",
        "ttl-zero-during-transit" : "0000001100000000",
        "unknown-header-type" : "0000010000000001",
        "unknown-option" : "0000010000000010",
    }[icmpv6_type]


# TODO: implement ranges
def _normalize_rt_type(rt_type):
    try:
        lrt, rrt = rt_type.split(':')
        return lrt, rrt
    except ValueError:
        return "{0:08b}".format(int(rt_type))
    else:
        raise Exception("Range not implemented on field: rt_type")


def _normalize_ipv6header(header):
    return "{0:08b}".format(int(header))


def _normalize_frag_id(frag_id):
    return "{0:032b}".format(frag_id)

# TODO: implement ranges
def _normalize_ah_spi(ah_spi):
    try:
        lspi, rspi = ah_spi.split(':')
        return lspi, rspi
    except ValueError:
        return "{0:032b}".format(int(ah_spi))
    else:
        raise Exception("Range not implemented on field: ah.spi")


def _normalize_ah_res(ah_res):
    return "{0:016b}".format(int(ah_res))


def _normalize_mh_type(mh_type):
    return "{0:08b}".format(int(mh_type))


# XXX: refactor and move to own utility module
def field_value_to_bitvector(field):
    """ Converts field value to its bitvector representation.

    Keyword arguments:
    field -- a header field
    """

    if isinstance(field, Field):
        name, size, value = field.name, field.size, field.value
    elif isinstance(field, SwitchRuleField):
        name, size, value = field.name, FIELD_SIZES[field.name], field.value
    else:
        raise "field type not implemented:", type(field)

    vector = Vector(length=size)
    try:
        vector[:] = {
            "packet.ipv6.source" : normalize_ipv6_address,
            "packet.ipv6.destination" : normalize_ipv6_address,
            "packet.upper.sport" : normalize_upper_port,
            "packet.upper.dport" : normalize_upper_port,
            "interface" : _normalize_interface,
            "module" : _normalize_module,
            "module.ipv6header.header" : normalize_ipv6header_header,
            "module.limit" : _normalize_limit,
            "module.state" : _normalize_states,
            "packet.ipv6.proto" : normalize_ipv6_proto,
            "packet.ipv6.icmpv6.type" : _normalize_icmpv6_type,
            "module.ipv6header.rt.len" : _normalize_ipv6header,
            "module.ipv6header.rt.segsleft" : _normalize_ipv6header,
            "module.ipv6header.ah.len" : _normalize_ipv6header,
            "module.ipv6header.dst.len" : _normalize_ipv6header,
            "module.ipv6header.frag.len" : _normalize_ipv6header,
            "module.ipv6header.hbh.len" : _normalize_ipv6header,
            "module.ipv6header.hl.eq" : _normalize_ipv6header,
            "module.ipv6header.rt.type" : _normalize_rt_type,
            "module.ipv6header.frag.id" : _normalize_frag_id,
            "module.ipv6header.ah.res" : _normalize_ah_res,
            "module.ipv6header.ah.spi" : _normalize_ah_spi,
            "module.ipv6header.mh.type" : _normalize_mh_type
        }[name](value)
    except KeyError:
        raise Exception("Field not implemented: %s" % name)

    return vector


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

    size = lambda k: FIELD_SIZES[tag(k)]

    value = lambda k: k.get_first().value if k.get_first() is not None else ""

    if ast.has_child("-A"):
        ast = ast.get_child("-A")
    elif ast.has_child("-P"):
        ast = ast.get_child("-P")

    if not ast:
        return

    body = [
        Field(tag(f.value), size(f.value), value(f)) for f in ast if is_field(f)
    ]

    for field in body:
        field.vector = field_value_to_bitvector(field)

    action = get_action_from_ast(ast)

    chain = get_chain_from_ast(ast)
    rule = Rule(chain, action, body)

    return rule


def _get_rules_from_ast(ast):
    if _is_rule(ast):
        return [_ast_to_rule(ast)]
    elif not ast.has_children():
        return []
    else:
        return reduce(
            lambda l, r: l+r, [_get_rules_from_ast(st) for st in ast]
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
    model.rules = _get_rules_from_ast(ast)

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
