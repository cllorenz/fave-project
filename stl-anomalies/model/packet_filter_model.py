#!/usr/bin/env python3

import pprint

from model.rule import Rule

class PacketFilterModel(dict):
    def __init__(self, interfaces=None):
        super(PacketFilterModel, self).__init__()
        self.interfaces = interfaces if interfaces else {}

    def add_rule(self, rule, chain):
        assert(isinstance(rule, Rule))

        self.setdefault(chain, [])
        self[chain].append(rule)

    def add_interface(self, name):
        if not name in self.interfaces:
            self.interfaces[name] = len(self.interfaces)

    def __str__(self):
        pprint.pprint(
            {
                chain : [
                    str(rule) for rule in rules
                ] for chain, rules in self.items()
            }
        )


    def analyse(self, chain, verbose=False):
        chain = self[chain.lower()]

        shadowed_rules = set()

        for rule1 in chain:
#            if rule1.index != 526: continue

            for rule2 in chain:
                if rule1.index >= rule2.index: continue
#                if rule2.index != 537: continue

                if rule2.subseteq(rule1):
                    shadowed_rules.add(rule2)

                    if verbose:
                        print("{} is shadowed by {}".format(rule2.index, rule1.index))
                        print("\t {}\n\t {}".format(rule1.raw, rule2.raw))

                else:
                    pass # the rules just overlap

        print("  Shadowed Rules ({}):".format(len(shadowed_rules)))
        for rule in sorted(shadowed_rules, key=lambda r: r.index):
            print("    {}: {}".format(rule.raw_rule_no, rule.raw))
