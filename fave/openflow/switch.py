#!/usr/bin/env python2

from netplumber.mapping import Mapping
from netplumber.model import Model


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
        return SwitchRuleField(
            j["name"],
            j["value"]
        )


class SwitchRuleAction(object):
    def __init__(self,name,value):
        self.name = name


class Forward(SwitchRuleAction):
    def __init__(self,ports = []):
        super(self,Forward).__init__("forward")
        self.ports = ports

    def to_json(self):
        return {
            "name" : self.name,
            "ports" : self.ports
        }

    @staticmethod
    def from_json(j):
        return Forward(ports=j["ports"])


class Rewrite(SwitchRuleAction):
    def __init__(self,rw=[]):
        super(self,Rewrite).__init__("rewrite")
        self.rw = rw # type: Field()

    def to_json(self):
        return {
            "name" : self.name,
            "rw" : [field.to_json() for field in self.rw],
        }

    @staticmethod
    def from_json(j):
        return Rewrite(
            rw=[Field.from_json(field) for field in j["rw"]]
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
        return Match(
            fields = [SwitchRuleField(field) for field in j["fields"]]
        )


class SwitchRule(Model):
    def __init__(self,node,idx,match=None,actions=[]):
        super(self,SwitchRule).__init__(node,type="switch_rule")
        self.idx = idx
        self.match = match
        self.actions = actions

    def to_json(self):
        return {
            "idx" : self.idx,
            "match" : self.match.to_json() if self.match else None,
            "actions" : [action.to_json() for action in self.actions]
        }

    @staticmethod
    def from_json(j):
        actions = {
            "forward" : Forward,
            "rewrite" : Rewrite
        }

        return SwitchRule(
            idx = j["idx"],
            match = Match.from_json(j["match"]),
            actions = [actions[action["name"]].from_json(action) for action in j["actions"]]
        )


class SwitchCommand(Model):
    def __init__(self,node,command,rule):
        super(self,SwitchCommand).__init__(node,type="switch_command")
        self.command = command
        self.rule = rule

    def to_json(self):
        j = super(SwitchCommand,self).to_json()
        j["command"] = self.command
        j["rule"] = self.rule.to_json()
        return j

    @staticmethod
    def from_json(j):
        return SwitchCommand(
            j["node"],
            j["command"],
            SwitchRule.from_json(j["rule"])
        )


class SwitchModel(Model):
    def __init__(self,node,ports=0,rules=[]):
        super(SwitchModel,self).__init__(node,"switch")
        self.mapping = Mapping(length=0)
        self.ports = ports
        self.rules = rules

    def to_json(self):
        j = super(SwitchModel,self).to_json()
        j["mapping"] = self.mapping
        j["ports"] = self.ports
        j["rules"] = [rule.to_json() for rule in self.rules]
        return 

    @staticmethod
    def from_json(j):
        of = SwitchModel(j["node"])
        of.mapping=Mapping.from_json(j["mapping"])
        of.ports = j["ports"]
        of.rules = [SwitchRule.from_json(rj) for rj in j["rules"]]
        return of

    def add_rule(self,idx,rule):
        self.rules.insert(idx,rule)

    def remove_rule(self,idx):
        del self.rules[idx]

    def update_rule(self,idx,rule):
        self.remove_rule(idx)
        self.add_rule(idx,rule)
