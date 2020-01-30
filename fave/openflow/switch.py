#!/usr/bin/env python2

""" This module provides models for switch rule fields, matches, actions, switch
    rules, switches, and switch commands.
"""

import sys
import getopt
import json

try:
    from ip6np.ip6np_util import field_value_to_bitvector, VectorConstructionError
except ImportError:
    from ip6np_util import field_value_to_bitvector, VectorConstructionError

from netplumber.vector import Vector, set_field_in_vector
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.model import Model

from util.print_util import eprint
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from util.collections_util import list_sub

from util.aggregator_utils import connect_to_fave


class SwitchRuleField(object):
    """ This class provides a model for switch rules.
    """

    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.vector = None


    def value_to_vector_str(self):
        """ Transforms the value into a vector string.
        """

        if not isinstance(self.value, Vector):
            try:
                self.vectorize()
            except VectorConstructionError:
                pass


    def vectorize(self):
        """ Transforms value into a vector representation.
        """

        if not isinstance(self.value, Vector):
            self.vector = field_value_to_bitvector(self)


    # XXX: deprecated
    def enlarge(self, nlength):
        """ Enlarges value in vector representation by length.

        Keyword arguments:
        nlength -- the length to be added
        """
        if isinstance(self.value, Vector):
            self.value.enlarge(nlength)

        else:
            try:
                self.vectorize()
                self.vector.enlarge(nlength)
            except VectorConstructionError:
                pass



    def unleash(self):
        """ Returns a tuple representation.
        """
        return self.name, FIELD_SIZES[self.name], self.value


    def to_json(self):
        """ Converts the field to JSON.
        """

        return {
            "name" : self.name,
            "value" : self.value.vector if isinstance(self.value, Vector) else self.value
        }


    @staticmethod
    def from_json(j):
        """ Creates a switch rule field from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        name = j["name"]
        value = j["value"]

        if Vector.is_vector(value, name=name):
            value = Vector.from_vector_str(value)
            assert value.length == FIELD_SIZES[name]


        return SwitchRuleField(
            name,
            value
        )


    def __eq__(self, other):
        assert isinstance(other, SwitchRuleField)

        return self.name == other.name and self.value == other.value


class SwitchRuleAction(object):
    """ Abstract class for switch rule action models.
    """

    def __init__(self, name):
        self.name = name


    def values_to_vector_str(self):
        """ Transforms all field values into vector strings.
        """
        pass


class Forward(SwitchRuleAction):
    """ This class provides a forward action.
    """

    def __init__(self, ports=None):
        super(Forward, self).__init__("forward")
        self.ports = ports if ports is not None else []


    def __str__(self):
        return "forward:[%s]" % ",".join([str(p) for p in self.ports])


    def to_json(self):
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name,
            "ports" : self.ports
        }


    @staticmethod
    def from_json(j):
        """ Constructs a forward action from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """
        if isinstance(j, str):
            j = json.loads(j)

        return Forward(ports=j["ports"])


    def __eq__(self, other):
        if not isinstance(other, Forward):
            return False

        return self.ports == other.ports


class Rewrite(SwitchRuleAction):
    """ This class provides a rewrite action.
    """

    def __init__(self, rewrite=None):
        super(Rewrite, self).__init__("rewrite")
        self.rewrite = rewrite if rewrite is not None else [] # type: [Field()]


    def __str__(self):
        return "rewrite:%s" % ",".join(["%s->%s" % (f.name, f.value) for f in self.rewrite])


    def to_json(self):
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name,
            "rw" : [field.to_json() for field in self.rewrite],
        }


    # XXX: deprecated
    def enlarge(self, length):
        """ Enlarges all vectors by length.

        Keyword arguments:
        length -- the length to be added
        """
        for field in self.rewrite:
            field.enlarge(length)


    @staticmethod
    def from_json(j):
        """ Constructs a rewrite action from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return Rewrite(
            rewrite=[SwitchRuleField.from_json(field) for field in j["rw"]]
        )


    def __eq__(self, other):
        if not isinstance(other, Rewrite):
            return False

        return len(self.rewrite) == len(other.rewrite) or \
            all([a == b for a, b in zip(self.rewrite, other.rewrite)])


    def values_to_vector_str(self):
        for field in self.rewrite:
            field.value_to_vector_str()


class Miss(SwitchRuleAction):
    """ This class provides a miss action.
    """

    def __init__(self):
        super(Miss, self).__init__("miss")


    def __str__(self):
        return self.name


    def to_json(self):
        """ Converts the action to JSON.
        """

        return {
            "name" : self.name
        }


    @staticmethod
    def from_json(_j):
        """ Constructs a miss action from JSON.
        """
        return Miss()


    def __eq__(self, other):
        return isinstance(other, Miss)


class Match(list):
    """ This class provides models for switch rule matches.
    """

    def __init__(self, fields=None, vectorize=False):
        super(Match, self).__init__(fields if fields is not None else [])
        self.vector = self.vectorize() if vectorize else None


    def vectorize(self):
        for field in self:
            field.vectorize()

        return Vector(
            sum([f.value.length for f in self])
        ) if self != [] else Vector(0)


    def enlarge(self, length):
        """ Enlarges all vectors by length.

        Keyword arguments:
        length -- the length to be added
        """

        if self.vector:
            self.vector.enlarge(length)


    def to_json(self):
        """ Converts the match to JSON.
        """

        return {
            "fields" : [field.to_json() for field in self],
        }

    def calc_vector(self, mapping):
        """ Aligns all vectors according to a mapping.

        Keyword arguments:
        mapping -- the mapping
        """

        assert isinstance(mapping, Mapping)

        vector = Vector(mapping.length)
        for field in self:
            field.vectorize()
            set_field_in_vector(mapping, vector, field.name, field.vector.vector)

        self.vector = vector


    def __str__(self):
        return ",".join(["%s=%s" % (f.name, f.value) for f in self])


    @staticmethod
    def from_json(j):
        """ Construct a match from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if not j:
            return Match()

        if isinstance(j, str):
            j = json.loads(j)

        return Match(
            fields=[SwitchRuleField.from_json(f) for f in j["fields"]]
        )


    def filter(self, field):
        if isinstance(field, SwitchRuleField):
            name = field.name
        elif isinstance(field, str):
            name = field
        else:
            raise Exception("cannot filter match for a field of type: %s" % type(field))

        for f in self:
            if f.name == name:
                self.remove(f)


class SwitchRule(Model):
    """ This class provides a model for switch rules.
    """

    def __init__(self, node, tid, idx, in_ports=None, match=None, actions=None, mapping=None):
        if not mapping:
            mapping = SwitchRule._match_to_mapping(match)
        super(SwitchRule, self).__init__(node, mtype="switch_rule", mapping=mapping)
        self.tid = tid
        self.idx = idx
        self.in_ports = in_ports if in_ports is not None else []
        self.match = match if match else Match()
        self.actions = actions if actions is not None else []


    def __hash__(self):
        return hash(
            "%s.%s" % (self.tid, self.idx) +
            str(self.match) +
            ",".join(str(a) for a in self.actions)
        )

    @staticmethod
    def _match_to_mapping(match):
        mapping = Mapping()

        if not match:
            return mapping

        for field in match:
            mapping.extend(field.name)

        return mapping


    def calc_vector(self, mapping):
        """ Aligns all vectors according to a mapping.

        Keyword arguments:
        mapping -- the mapping
        """
        self.match.calc_vector(mapping)
        for action in self.actions:
            action.values_to_vector_str()


    def enlarge(self, length):
        """ Enlarges all vectors to length.

        Keyword arguments:
        length -- the new length
        """

        self.match.enlarge(length)
        for action in self.actions:
            if isinstance(action, Rewrite):
                action.enlarge(length)


    def enlarge_vector_to_length(self, length):
        """ Enlarges the rule's vector to a certain length.

        Keyword arguments:
        length -- the target length
        """
        self.match.enlarge(length - self.mapping.length)


    def to_json(self):
        """ Converts the rule to JSON.
        """

        for f in self.match:
            self.mapping.extend(f.name)

        for rw in [a for a in self.actions if isinstance(a, Rewrite)]:
            for f in rw.rewrite:
                self.mapping.extend(f.name)

        return {
            "node" : self.node,
            "tid" : self.tid,
            "idx" : self.idx,
            "in_ports" : self.in_ports,
            "match" : self.match.to_json() if self.match else None,
            "actions" : [action.to_json() for action in self.actions],
            "mapping" : self.mapping.to_json()
        }


    @staticmethod
    def from_json(j):
        """ Constructs a switch rule from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        actions = {
            "forward" : Forward,
            "rewrite" : Rewrite,
            "miss" : Miss
        }

        return SwitchRule(
            node=j["node"],
            tid=int(j["tid"]) if isinstance(j["tid"], str) and j["tid"].isdigit() else j["tid"],
            idx=int(j["idx"]),
            in_ports=j["in_ports"],
            match=Match.from_json(j["match"]),
            actions=[actions[action["name"]].from_json(action) for action in j["actions"]],
            mapping=Mapping.from_json(j["mapping"])
        )

    def __str__(self):
        return "%s\ntid: %s\nidx: %s\nmatch:\n\t%s\nactions:\n\t%s\n" % (
            super(SwitchRule, self).__str__(),
            self.tid,
            self.idx,
            self.match,
            self.actions
        )


    def __eq__(self, other):
        assert isinstance(other, SwitchRule)

        return all([
            self.node == other.node,
            self.tid == other.tid,
            self.idx == other.idx,
            self.in_ports == other.in_ports,
            self.match == other.match,
            self.actions == other.actions,
            self.mapping == other.mapping
        ])


class SwitchCommand(object):
    """ This class provides switch commands for FaVe.
    """

    def __init__(self, node, command, rule):
        self.node = node
        self.type = "switch_command"
        self.command = command
        self.rule = rule


    def to_json(self):
        """ Converts the switch command to JSON.
        """
        return {
            "node" : self.node,
            "type" : self.type,
            "command" : self.command,
            "rule" : self.rule.to_json(),
            "mapping" : self.rule.mapping.to_json()
        }


    @staticmethod
    def from_json(j):
        """ Constructs a switch command from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return SwitchCommand(
            j["node"],
            j["command"],
            SwitchRule.from_json(j["rule"])
        )


class SwitchModel(Model):
    """ This class provides a switch model.
    """

    def __init__(self, node, ports=None, rules=None):
        ports = ports if ports is not None else []

        super(SwitchModel, self).__init__(node, "switch")
        self.mapping = Mapping(length=0)
        self.ports = {str(p) : p for p in ports}
        self.tables = {"1" : []}
        self.rules = rules if rules is not None else []


    def to_json(self):
        """ Converts the switch to JSON.
        """
        j = super(SwitchModel, self).to_json()
        j["mapping"] = self.mapping
        j["ports"] = self.ports
        j["tables"] = {t:[r.to_json() for r in self.tables[t]] for t in self.tables}
        j["rules"] = [rule.to_json() for rule in self.rules]
        return j

    @staticmethod
    def from_json(j):
        """ Constructs a switch from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        ofm = SwitchModel(j["node"])
        ofm.mapping = Mapping.from_json(j["mapping"]) if j["mapping"] else Mapping()
        ofm.ports = j["ports"]

        ofm.tables = {}
        for table in j["tables"]:
            ntable = []
            for rule in j["tables"][table]:
                rule = SwitchRule.from_json(rule)
                ntable.insert(rule.idx, rule)
            ofm.tables[table] = ntable

        for rule in j["rules"]:
            rule = SwitchRule.from_json(rule)
            ofm.rules.insert(rule.idx, rule)

        return ofm


    def add_rule(self, idx, rule):
        """ Adds a rule to the switch.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule
        """
        self.rules.insert(idx, rule)
        self.tables["1"].insert(idx, rule)


    def remove_rule(self, idx):
        """ Removes a rule from the switch.

        Keyword arguments:
        idx -- a rule index
        """
        del self.tables["1"][idx]
        del self.rules[idx]


    def update_rule(self, idx, rule):
        """ Replaces a rule in the switch.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule
        """

        self.remove_rule(idx)
        self.add_rule(idx, rule)


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        smm = super(SwitchModel, self).__sub__(other)
        rules = list_sub(self.rules, other.rules)

        res = SwitchModel(
            smm.node,
            ports=smm.ports,
            rules=rules
        )
        res.tables = smm.tables
        res.wiring = smm.wiring
        res.mapping = smm.mapping

        return res


def fieldify(field):
    """ Converts a field tuple to a field model.

    Keyword arguments:
    field -- a tuple (field_name, field_value)
    """

    fld, val = field
    try:
        return SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD[fld], val)
    except KeyError:
        return SwitchRuleField(fld, val)


def print_help():
    """ Prints usage message to stderr.
    """

    eprint(
        "switch -ad -t <id> -i <index> [-f <fields>] [-c <commands>]",
        "\t-a add device or links (default)",
        "\t-d delete device or links",
        "\t-n <id> apply command for node <id>",
        "\t-t <id> apply command for table <id>",
        "\t-i <index> apply command for the rule <index> (default: 0)",
        "\t-f <fields> add a rule matching a list of fields: k1=v1, k2=v2, ...",
        "\t-c <commands> add a rule with applying a list of actions: c1=a1;c2=a2;...",
        "\t-p <ports> add a rule with applying a list of ports: p1,p2,p3, ...",
        sep="\n"
    )


def main(argv):
    """ Provides functionality to interact with switches in FaVe.
    """

    command = "add"
    node = ""
    table = 1
    cmd = None
    idx = 0
    fields = []
    actions = []
    in_ports = []

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "hadun:t:i:f:c:p:"))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)
        elif opt == '-a':
            command = 'add'
        elif opt == '-d':
            command = 'del'
        elif opt == '-u':
            command = 'upd'
        elif opt == '-n':
            node = arg
        elif opt == '-t':
            table = int(arg)
        elif opt == '-i':
            idx = int(arg)
        elif opt == '-f':
            fields = []
            for field in arg.split(';'):
                fields.append(fieldify(field.split('=')))
                if field.startswith('tcp') or field.startswith('udp'):
                    fields.append(SwitchRuleField('ip_proto', field[:3]))
                elif field.startswith('icmp'):
                    fields.append(SwitchRuleField('ip_proto', field[:4]))

        elif opt == '-c':
            for action in arg.split(','):
                cmd, body = action.split('=')
                if cmd == 'fd':
                    actions.append(Forward([p for p in body.split(';')]))

                elif cmd == 'rw':
                    rwfields = [fieldify(f.split(':')) for f in body.split(';')]
                    actions.append(Rewrite(rwfields))

        elif opt == '-p':
            in_ports = [p[len(node)+1:] for p in arg.split(',')]

    if command == 'add':
        rule = SwitchRule(
            node, table, idx,
            in_ports=in_ports,
            match=Match(fields),
            actions=actions
        )
        cmd = SwitchCommand(node, 'add_rule', rule)


    elif command == 'del':
        rule = SwitchRule(
            table, table, idx,
            in_ports=in_ports,
            match=Match([]),
            actions=[]
        )
        cmd = SwitchCommand(node, 'remove_rule', rule)


    elif command == 'upd':
        rule = SwitchRule(
            table, table, idx,
            in_ports=in_ports,
            match=Match(fields),
            actions=actions
        )
        cmd = SwitchCommand(node, 'update_rule', rule)


    else:
        print_help()
        sys.exit(2)


    fave = connect_to_fave()
    fave.send(json.dumps(cmd.to_json()))
    fave.close()


if __name__ == "__main__":
    main(sys.argv[1:])
