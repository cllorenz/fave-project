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
import argparse
import json

from copy import copy

from rule.rule_model import Rule, RuleField, Forward, Rewrite, Match

from devices.abstract_device import AbstractDeviceModel

from util.match_util import OXM_FIELD_TO_MATCH_FIELD

from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
from util.aggregator_utils import connect_to_fave, fave_sendmsg


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
            [Rule.from_json(r) for r in j["rules"]]
        )


class SwitchModel(AbstractDeviceModel):
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
            j["table_ids"] = {t:i for t, i in self.table_ids.iteritems()}
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
                Rule.from_json(r) for r in rules
            ] for table, rules in j['tables'].iteritems()
        }
        ofm.ports = j['ports']

        return ofm


    def add_rules(self, rules):
        for rule in rules:
            rule.tid = self.node+'.1'
        super(SwitchModel, self).add_rules(rules)


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
        self.add_rules(idx, [rule])


    def __sub__(self, other):
        assert self.node == other.node
        assert self.type == other.type

        res = SwitchModel(
            self.node,
            ports=self.ports
        )

        res.tables = copy(self.adds)

        return res


def fieldify(field):
    """ Converts a field tuple to a field model.

    Keyword arguments:
    field -- a tuple (field_name, field_value)
    """

    fld, val = field
    return RuleField(OXM_FIELD_TO_MATCH_FIELD[fld], val)


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

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-a', '--add',
        dest='command',
        action='store_const',
        const='add',
        default='add'
    )
    parser.add_argument(
        '-d', '--delete',
        dest='command',
        action='store_const',
        const='del',
        default='add'
    )
    parser.add_argument(
        '-u', '--update',
        dest='command',
        action='store_const',
        const='upd',
        default='add'
    )
    parser.add_argument(
        '-U', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-n', '--node',
        dest='node',
        default=''
    )
    parser.add_argument(
        '-t', '--table',
        dest='table',
        default='1'
    )
    parser.add_argument(
        '-i', '--index',
        dest='index',
        type=int,
        default=0
    )
    parser.add_argument(
        '-f', '--fields',
        dest='fields',
        type=_fields_to_match,
        default=[]
    )
    parser.add_argument(
        '-c', '--commands',
        dest='actions',
        type=_commands_to_actions,
        default=[]
    )
    parser.add_argument(
        '-p', '--ports',
        dest='in_ports',
        type=lambda p: p.split(','),
        default=[]
    )
    parser.add_argument(
        '-r', '--rules',
        dest='rules',
        type=lambda rules: [r.split('$') for r in rules.split('#')],
        default=[]
    )

    args = parser.parse_args(argv)

    table = args.node+'.'+args.table

    cmd = None

    if args.command == 'add':
        if args.rules:

            switch_rules = []
            switch_rules = [
                Rule(
                    node,
                    int(table),
                    int(idx),
                    [p for p in in_ports.split(',') if p],
                    Match(_fields_to_match(fields)),
                    _commands_to_actions(commands)
                ) for node, table, idx, in_ports, fields, commands in args.rules
            ]
            cmd = SwitchCommand(node, 'add_rules', switch_rules)
        else:
            rule = Rule(
                args.node, table, args.index,
                in_ports=args.in_ports,
                match=Match(args.fields),
                actions=args.actions
            )
            cmd = SwitchCommand(args.node, 'add_rules', [rule])


    elif args.command == 'del':
        rule = Rule(
            table, table, args.index,
            in_ports=args.in_ports,
            match=Match([]),
            actions=[]
        )
        cmd = SwitchCommand(args.node, 'remove_rule', rule)


    elif args.command == 'upd':
        rule = Rule(
            table, table, args.index,
            in_ports=args.in_ports,
            match=Match(args.fields),
            actions=args.actions
        )
        cmd = SwitchCommand(args.node, 'update_rule', rule)


    else:
        parser.print_help()
        sys.exit(2)


    fave = connect_to_fave(
        FAVE_DEFAULT_UNIX
    ) if args.use_unix else connect_to_fave(
        FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
    )
    fave_sendmsg(fave, json.dumps(cmd.to_json()))
    fave.close()


if __name__ == "__main__":
    main(sys.argv[1:])
