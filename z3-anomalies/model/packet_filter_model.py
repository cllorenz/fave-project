#!/usr/bin/env python3

import pprint

from model.rule import Rule

from z3 import And, Not, Solver, sat, unsat

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

        solver = Solver()

        shadowed_rules = set()

        for rule1 in chain:
            for rule2 in chain:
                if rule1.index >= rule2.index: continue

                f1 = And(rule1.to_z3(), rule2.to_z3())

                if solver.check(f1) == unsat: # disjoint rules
                    continue

                f2 = And(Not(rule1.to_z3()), rule2.to_z3())
                f3 = And(rule1.to_z3(), Not(rule2.to_z3()))

                bf2 = solver.check(f2)
                bf3 = solver.check(f3)

                if bf2 == unsat and bf3 == unsat:
                    shadowed_rules.add(rule2)
                    if verbose:
                        print("{} is shadowed by {} (equal match)".format(rule2.index, rule1.index))
                        print("\t {}\n\t {}".format(rule1.raw, rule2.raw))

                elif bf2 == unsat and bf3 == sat:
                    shadowed_rules.add(rule2)
                    if verbose:
                        print("{} is shadowed by {} (included match)".format(rule2.index, rule1.index))
                        print("\t {}\n\t {}".format(rule2.raw, rule1.raw))

                elif bf2 == sat and bf3 == unsat:
                    pass # rule1 is included in rule2 which is not a relevant anomaly

                else:
                    pass # the rules just overlap

        print("  Shadowed Rules ({}):".format(len(shadowed_rules)))
        for rule in sorted(shadowed_rules, key=lambda r: r.index):
            print("    {}: {}".format(rule.raw_rule_no, rule.raw))
