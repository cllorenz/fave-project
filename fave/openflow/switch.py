#!/usr/bin/env python2

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

""" This module provides models for switches and switch commands.
"""

import sys
import getopt
import json

from copy import deepcopy

from openflow.rule import SwitchRule, SwitchRuleField, Forward, Rewrite, Match

from netplumber.mapping import Mapping
from netplumber.model import Model

from util.print_util import eprint
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from util.collections_util import list_sub

from util.aggregator_utils import connect_to_fave, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX, fave_sendmsg


class SwitchCommand(object):
    """ This class provides switch commands for FaVe.
    """

    def __init__(self, node, command, rules):
        self.node = node
        self.type = "switch_command"
        self.command = command
        self.rules = rules


    def to_json(self):
        """ Converts the switch command to JSON.
        """
        return {
            "node" : self.node,
            "type" : self.type,
            "command" : self.command,
            "rules" : [r.to_json() for r in self.rules]
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
            [SwitchRule.from_json(r) for r in j["rules"]]
        )


class SwitchModel(Model):
    """ This class provides a switch model.
    """

    def __init__(self, node, ports=None, rules=None, table_ids=None):
        ports = ports if ports is not None else []

        super(SwitchModel, self).__init__(node, "switch")
        self.ports = {node+"."+str(p) : node+".1" for p in ports}
        self.tables = {node+".1" : rules if rules is not None else []}

        if table_ids:
            self.table_ids = table_ids


    def to_json(self):
        """ Converts the switch to JSON.
        """
        j = super(SwitchModel, self).to_json()
        j["ports"] = self.ports
        j["tables"] = {
            table : [
                r.to_json() for r in rules
            ] for table, rules in self.tables.iteritems()
        }
        if hasattr(self, 'table_ids'):
            j["table_ids"] = { t:i for t, i in self.table_ids.iteritems() }
        return j

    @staticmethod
    def from_json(j):
        """ Constructs a switch from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        table_ids = j['table_ids'] if 'table_ids' in j else None

        ofm = SwitchModel(j['node'], table_ids=table_ids)
        ofm.tables = {
            table : [
                SwitchRule.from_json(r) for r in rules
            ] for table, rules in j['tables'].iteritems()
        }
        ofm.ports = j['ports']

        return ofm


    def add_rule(self, idx, rule):
        """ Adds a rule to the switch.

        Keyword arguments:
        idx -- a rule index
        rule -- a rule
        """

        rule.tid = self.node+'.1'
        super(SwitchModel, self).add_rule(rule)


    def remove_rule(self, idx):
        """ Removes a rule from the switch.

        Keyword arguments:
        idx -- a rule index
        """
        super(SwitchModel, self).remove_rule(idx)
        del self.tables[self.node+".1"][idx]


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

        res = SwitchModel(
            self.node,
            ports=self.ports
        )

        res.tables = deepcopy(self.adds)

        return res


def fieldify(field):
    """ Converts a field tuple to a field model.

    Keyword arguments:
    field -- a tuple (field_name, field_value)
    """

    fld, val = field
    return SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD[fld], val)


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


def _fields_to_match(fields):
    match = []
    for field in [f for f in fields.split(';') if f]:
        match.append(fieldify(field.split('=')))
        if field.startswith('tcp') or field.startswith('udp'):
            match.append(fieldify(('ip_proto', field[:3])))
        elif field.startswith('icmp'):
            match.append(fieldify(('ip_proto', field[:4])))

    return match


def _commands_to_actions(commands):
    actions = []
    for action in [c for c in commands.split(',') if c]:
        cmd, body = action.split('=')
        if cmd == 'fd':
            actions.append(Forward([p for p in body.split(';')]))

        elif cmd == 'rw':
            rwfields = [fieldify(f.split(':')) for f in body.split(';')]
            actions.append(Rewrite(rwfields))

    return actions


def main(argv):
    """ Provides functionality to interact with switches in FaVe.
    """

    command = "add"
    node = ""
    table = "1"
    cmd = None
    idx = 0
    fields = []
    actions = []
    in_ports = []
    rules = []
    use_unix = False

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "haduUn:t:i:f:c:p:r:"))
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
        elif opt == '-U':
            use_unix = True
        elif opt == '-n':
            node = arg
        elif opt == '-t':
            table = arg
        elif opt == '-i':
            idx = int(arg)
        elif opt == '-f':
            fields = _fields_to_match(arg)
        elif opt == '-c':
            actions = _commands_to_actions(arg)
        elif opt == '-p':
            in_ports = arg.split(',')
        elif opt == '-r':
            rules = [r.split('$') for r in arg.split('#')]

    table = node+'.'+table

    if command == 'add':
        if rules:
            switch_rules = []
            switch_rules = [
                SwitchRule(
                    node,
                    int(table),
                    int(idx),
                    [p for p in in_ports.split(',') if p],
                    Match(_fields_to_match(fields)),
                    _commands_to_actions(commands)
                ) for node, table, idx, in_ports, fields, commands in rules
            ]
            cmd = SwitchCommand(node, 'add_rules', switch_rules)
        else:
            rule = SwitchRule(
                node, table, idx,
                in_ports=in_ports,
                match=Match(fields),
                actions=actions
            )
            cmd = SwitchCommand(node, 'add_rules', [rule])


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


    fave = connect_to_fave(FAVE_DEFAULT_UNIX) if use_unix else connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)
    fave_sendmsg(fave, json.dumps(cmd.to_json()))
    fave.close()


if __name__ == "__main__":
    main(sys.argv[1:])
