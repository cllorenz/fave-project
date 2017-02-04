import json


from netplumber.vector import Vector
from netplumber.mapping import field_sizes
from packet_filter import PacketFilterModel
from packet_filter import Field
from packet_filter import Rule


def is_rule(ast):
    return ast.has_child("-A") or ast.has_child("-I")

def normalize_ipv6_address(addr):
    laddr,raddr = addr.split("::")
    laddr = laddr.split(":")
    if raddr:
        raddr = raddr.split(":")
        laddr += ["0" for _i in range(8-len(laddr)-len(raddr))] + raddr
    return "".join([bin(int(block,16))[2:] for block in laddr])


def field_value_to_bitvector(field):
    vector = Vector(length=field.size)

    if field.name in [ "packet.ipv6.source", "packet.ipv6.destination" ]:
        addr,cidr = field.value.split("/")
        addr = normalize_ipv6_address(addr)
        if cidr and int(cidr) < 128:
            vector[:cidr] = addr
        else:
            vector[:field.size] = addr
        vector[:] = addr

    elif field.name in [ "packet.upper.sport","packet.upper.dport" ]:
        vector[:] = "{0:016b}".format(int(field.value))

    elif field.name == "interface":
        if field.value == "lo":
            interface = "0000000000000001"
        else:
            interface = bin(int(field.value,16))[2:]
        vector[:] = interface

    elif field.name == "module":
        vector[:vector.length] = {
            "ipv6header":"00000001",
            "limit":"00000010",
            "state":"00000011"
        }[field.value]

    elif field.name == "module.ipv6header.header":
        vector[:] = {"ipv6-route":"00101011"}[field.value]

    elif field.name == "module.limit":
        # fields have the format value/unit
        val,unit = field.value.split("/")
        factor = {
            None : 3600,
            "sec" : 1,
            "min" : 60,
            "hour" : 3600, 
            "day" : 86400
        }[unit]
        vector[:] = "{0:032b}".format(int(val) * factor)

    elif field.name == "module.state":
        states = field.value.split(",") if "," in field.value else [field.value]
        to_bit = lambda x: {"NEW":1,"RELATED":2,"ESTABLISHED":4,"INVALID":8}[x]
        bitmap = reduce(lambda x,y: x|y, map(to_bit, states))
        vector[:] = "{0:08b}".format(bitmap)

    elif field.name == "packet.ipv6.proto":
        vector[:] = {
            "icmpv6":"00111010",
            "tcp" : "00000110",
            "udp" : "00010001",
        }[field.value]

    elif field.name == "packet.ipv6.icmpv6.type":
        vector[:] = {
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
        }[field.value]

    # TODO: implement more fields
    else:
        raise Exception("Field not implemented: %s" % field.name)

    return vector


def ast_to_rule(ast):
    tags = {
        "-i":"interface",
        "-s":"packet.ipv6.source",
        "--source":"packet.ipv6.source",
        "-d":"packet.ipv6.destination",
        "--destination":"packet.ipv6.destination",
        "-p":"packet.ipv6.proto",
        "--icmpv6-type":"packet.ipv6.icmpv6.type",
        "--dport":"packet.upper.dport",
        "--sport":"packet.upper.sport",
        "-m":"module",
        "--limit":"module.limit",
        "--state":"module.state",
        "--header":"module.ipv6header.header",
    }

    tag = lambda k: tags[k]

    is_field = lambda f: tags.has_key(f.value)

    size = lambda k: field_sizes[tag(k)]

    value = lambda k: k[0].value if len(k) >= 1 else "" #TODO: ugly af

    body = [
        Field(tag(f.value), size(f.value), value(f)) for f in ast if is_field(f)
    ]

    for field in body:
        field.vector = field_value_to_bitvector(field)

    action = value(ast.get_child("-j"))

    chain = get_chain_from_ast(ast)
    rule = Rule(chain,action,body)

    return rule

def get_rules_from_ast(ast):
    if is_rule(ast):
        return [ast_to_rule(ast)]
    elif not ast.has_children():
        return []
    else:
        return reduce(
            lambda l,r: l+r, map(
                lambda st: get_rules_from_ast(st),ast))


def get_chain_from_ast(ast):
    chain = ast.get_child("-A").get_last().value
    return {
        "input":"input_rules",
        "output":"output_rules",
        "forward":"forward_rules"
    }[chain.lower()]


def transform_ast_to_model(ast,node):
    model = PacketFilterModel(node)
    model.rules = get_rules_from_ast(ast)

    return model


def generate(ast,node):
    # transform AST to basic model
    model = transform_ast_to_model(ast,node)

    # generate vectors from rule tree
    model.generate_vectors()

    # expand negated fields
    model.expand_rules()

    # normalize vector length
    model.normalize()

    # put the rules into their chains
    model.finalize()

    # generate model
    return model.to_json()
