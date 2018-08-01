#!/usr/bin/env python2

import sys
import getopt
import socket
import json

from netplumber.mapping import Mapping
from netplumber.model import Model

from util.print_util import eprint

from util.match_util import OXM_FIELD_TO_MATCH_FIELD

from util.collections_util import list_sub

class SwitchRuleField(object):
    def __init__(self,name,value):
        self.name = name
        self.value = value

    def to_json(self):
        return {
            "name" : self.name,
            "value" : self.value
        }

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        return SwitchRuleField(
            j["name"],
            j["value"]
        )


class SwitchRuleAction(object):
    def __init__(self,name):
        self.name = name


class Forward(SwitchRuleAction):
    def __init__(self,ports=[]):
        super(Forward,self).__init__("forward")
        self.ports = ports

    def to_json(self):
        return {
            "name" : self.name,
            "ports" : self.ports
        }

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        return Forward(ports=j["ports"])


class Rewrite(SwitchRuleAction):
    def __init__(self,rw=[]):
        super(Rewrite,self).__init__("rewrite")
        self.rw = rw # type: [Field()]

    def to_json(self):
        return {
            "name" : self.name,
            "rw" : [field.to_json() for field in self.rw],
        }

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        return Rewrite(
            rw=[SwitchRuleField.from_json(field) for field in j["rw"]]
        )


class Match(list):
    def __init__(self,fields=[]):
        super(Match,self).__init__(fields)

    def to_json(self):
        return {
            "fields" : [field.to_json() for field in self],
        }

    @staticmethod
    def from_json(j):
        if not j:
            return Match()

        if type(j) == str:
            j = json.loads(j)

#        try:
        fields = [SwitchRuleField.from_json(f) for f in j["fields"]]
#        except:
#            fields = [fieldify(field) for field in j["fields"]]

        return Match(fields=fields)


class SwitchRule(Model):
    def __init__(self,node,tid,idx,match=None,actions=[],mapping=None):
        if not mapping:
            mapping = SwitchRule._match_to_mapping(match)
        super(SwitchRule,self).__init__(node,mtype="switch_rule",mapping=mapping)
        self.tid = tid
        self.idx = idx
        self.match = match
        self.actions = actions

    @staticmethod
    def _match_to_mapping(match):
        mapping = Mapping()

        if not match:
            return mapping

        for field in match:
            mapping.extend(field.name)

        return mapping


    def to_json(self):
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
        if type(j) == str:
            j = json.loads(j)

        actions = {
            "forward" : Forward,
            "rewrite" : Rewrite
        }

        return SwitchRule(
            node=j["node"],
            tid = int(j["tid"]) if type(j["tid"]) == str and j["tid"].isdigit() else j["tid"],
            idx = int(j["idx"]),
            match = Match.from_json(j["match"]),
            actions = [actions[action["name"]].from_json(action) for action in j["actions"]],
            mapping = Mapping.from_json(j["mapping"])
        )

    def __str__(self):
        return "%s\ntid: %s\nidx: %s\nmatch:\n\t%s\nactions:\n\t%s\n" % (super(SwitchRule,self).__str__(),self.tid,self.idx,self.match,self.actions)

class SwitchCommand(object):
    def __init__(self,node,command,rule):
        self.node = node
        self.type = "switch_command"
        self.command = command
        self.rule = rule

    def to_json(self):
        return {
            "node" : self.node,
            "type" : self.type,
            "command" : self.command,
            "rule" : self.rule.to_json(),
            "mapping" : self.rule.mapping.to_json()
        }

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        return SwitchCommand(
            j["node"],
            j["command"],
            SwitchRule.from_json(j["rule"])
        )


class SwitchModel(Model):
    def __init__(self,node,ports=[],rules=[]):
        super(SwitchModel,self).__init__(node,"switch")
        self.mapping = Mapping(length=0)
        self.ports = {str(p) : p for p in ports}
        self.tables = { 1 : [] }
        self.rules = rules

    def to_json(self):
        j = super(SwitchModel,self).to_json()
        j["mapping"] = self.mapping
        j["ports"] = self.ports
        j["tables"] = {t:[r.to_json() for r in self.tables[t]] for t in self.tables}
        j["rules"] = [rule.to_json() for rule in self.rules]
        return j

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        of = SwitchModel(j["node"])
        of.mapping=Mapping.from_json(j["mapping"]) if j["mapping"] else Mapping()
        of.ports = j["ports"]
        of.tables = {t:[SwitchRule.from_json(r) for r in j["tables"][t]] for t in j["tables"]}
        of.rules = [SwitchRule.from_json(rj) for rj in j["rules"]]
        return of

    def add_rule(self,idx,rule):
        self.rules.insert(idx,rule)
        self.tables["1"].insert(idx,rule)

    def remove_rule(self,idx):
        del self.tables["1"][idx]
        del self.rules[idx]

    def update_rule(self,idx,rule):
        self.remove_rule(idx)
        self.add_rule(idx,rule)

    def __sub__(self,other):
        assert(self.node == other.node)
        assert(self.type == other.type)

        sm = super(SwitchModel,self).__sub__(other)
        rules = list_sub(self.rules,other.rules)

        res = SwitchModel(
            sm.node,
            ports=sm.ports,
            rules=rules
        )
        res.tables = sm.tables
        res.wiring = sm.wiring
        res.mapping = sm.mapping

        return res


def fieldify(field):
    f,v = field
    try:
        return SwitchRuleField(OXM_FIELD_TO_MATCH_FIELD[f],v)
    except KeyError:
        return SwitchRuleField(f,v)

def print_help():
    eprint(
        "switch -ad -t <id> -i <index> [-f <fields>] [-c <commands>]",
        "\t-a add device or links (default)",
        "\t-d delete device or links",
        "\t-n <id> apply command for node <id>",
        "\t-t <id> apply command for table <id>",
        "\t-i <index> apply command for the rule <index> (default: 0)",
        "\t-f <fields> add a rule matching a list of fields: k1=v1,k2=v2,...",
        "\t-c <commands> add a rule with applying a list of actions: c1=a1;c2=a2;...",
        sep="\n"
    )

def main(argv):
    command = "add"
    node = ""
    table = 1
    cmd = None
    idx = 0
    fields = []
    actions = []

    try:
        opts,args = getopt.getopt(argv,"hadun:t:i:f:c:")
    except:
        print_help()
        sys.exit(2)

    for opt,arg in opts:
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
                    fields.append(SwitchRuleField('ip_proto',field[:3]))
                elif field.startswith('icmp'):
                    fields.append(SwitchRuleField('ip_proto',field[:4]))

        elif opt == '-c':
            for action in arg.split(','):
                cmd,body = action.split('=')
                if cmd == 'fd':
                    actions.append(Forward([p for p in body.split(';')]))

                elif cmd == 'rw':
                    fields = [fieldify(f.split('=')) for f in body.split(';')]
                    actions.append(Rewrite(fields))

    if command == 'add':
        rule = SwitchRule(node,table,idx,match=Match(fields),actions=actions)
        cmd = SwitchCommand(node,'add_rule',rule)


    elif command == 'del':
        rule = SwitchRule(table,table,idx,match=Match([]),actions=[])
        cmd = SwitchCommand(node,'remove_rule',rule)


    elif command == 'upd':
        rule = SwitchRule(table,table,idx,match=Match(fields),actions=actions)
        cmd = SwitchCommand(node,'update_rule',rule)


    else:
        print_help()
        sys.exit(2)


    aggregator = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    aggregator.connect("/tmp/np_aggregator.socket")

    #print cmd.to_json()
    aggregator.send(json.dumps(cmd.to_json()))

    aggregator.close()


if __name__ == "__main__":
    main(sys.argv[1:])

