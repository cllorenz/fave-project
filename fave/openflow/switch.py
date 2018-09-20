#!/usr/bin/env python2

""" This module provides models for switch rule fields, matches, actions, switch
    rules, switches, and switch commands.
"""

import sys
import getopt
import socket
import json

from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.model import Model
from util.print_util import eprint
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from util.collections_util import list_sub

from util.aggregator_utils import UDS_ADDR

class SwitchRuleField(object):
    """ This class provides a model for switch rules.
    """

    def __init__(self, name, value):
        self.name = name
        self.value = value


    def enlarge(self, nlength):
        self.value.enlarge(nlength)


    def unleash(self):
        return self.name, FIELD_SIZES[self.name], self.value


    def to_json(self):
        """ Converts the switch rule to JSON.
        """

        return {
            "name" : self.name,
            "value" : self.value
        }


    @staticmethod
    def from_json(j):
        """ Creates a switch rule from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return SwitchRuleField(
            j["name"],
            j["value"]
        )


class SwitchRuleAction(object):
    """ Abstract class for switch rule action models.
    """

    def __init__(self, name):
        self.name = name


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


class Match(list):
    """ This class provides models for switch rule matches.
    """

    def __init__(self, fields=None):
        super(Match, self).__init__(fields if fields is not None else [])


    def enlarge(self, length):
        for field in self:
            field.enlarge(length)


    def to_json(self):
        """ Converts the match to JSON.
        """

        return {
            "fields" : [field.to_json() for field in self],
        }


    def __str__(self):
        return ",".join(["%s=%s" % (f.name, f.value) for f in self.fields])


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


class SwitchRule(Model):
    """ This class provides a model for switch rules.
    """

    def __init__(self, node, tid, idx, match=None, actions=None, mapping=None):
        if not mapping:
            mapping = SwitchRule._match_to_mapping(match)
        super(SwitchRule, self).__init__(node, mtype="switch_rule", mapping=mapping)
        self.tid = tid
        self.idx = idx
        self.match = match
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


    def enlarge(self, length):
        self.match.enlarge(length)


    def to_json(self):
        """ Converts the rule to JSON.
        """

        return {
            "node" : self.node,
            "tid" : self.tid,
            "idx" : self.idx,
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
            "rewrite" : Rewrite
        }

        return SwitchRule(
            node=j["node"],
            tid=int(j["tid"]) if isinstance(j["tid"], str) and j["tid"].isdigit() else j["tid"],
            idx=int(j["idx"]),
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
        self.tables = {1 : []}
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
        ofm.tables = {t:[SwitchRule.from_json(r) for r in j["tables"][t]] for t in j["tables"]}
        ofm.rules = [SwitchRule.from_json(rj) for rj in j["rules"]]
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

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "hadun:t:i:f:c:"))
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
                    fields = [fieldify(f.split('=')) for f in body.split(';')]
                    actions.append(Rewrite(fields))

    if command == 'add':
        rule = SwitchRule(node, table, idx, match=Match(fields), actions=actions)
        cmd = SwitchCommand(node, 'add_rule', rule)


    elif command == 'del':
        rule = SwitchRule(table, table, idx, match=Match([]), actions=[])
        cmd = SwitchCommand(node, 'remove_rule', rule)


    elif command == 'upd':
        rule = SwitchRule(table, table, idx, match=Match(fields), actions=actions)
        cmd = SwitchCommand(node, 'update_rule', rule)


    else:
        print_help()
        sys.exit(2)


    aggregator = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    aggregator.connect(UDS_ADDR)

    aggregator.send(json.dumps(cmd.to_json()))

    aggregator.close()


if __name__ == "__main__":
    main(sys.argv[1:])

