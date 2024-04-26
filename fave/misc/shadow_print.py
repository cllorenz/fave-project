#!/usr/bin/env python3

import sys
import json

def _main(argv):
    shadowed_ids = {}

    with open('stdout.log', 'r') as sout:
        for line in sout.readlines():
            token = line.split()
            try:
                if not token[4] == 'DefaultShadowDetectionLogger':
                    continue

                shadowed_id = ((int(token[14].rstrip(')')) & 0xffffffff) >> 12)
                shadowing_id = ((int(token[18]) & 0xffffffff) >> 12)
                shadowed_ids[shadowed_id] = shadowing_id

            except IndexError:
                pass

    with open('bench/wl_tum/rulesets/tum-ruleset') as rs_:
        rules = {}
        default_rules = {}
        rule_counts = {}
        for line in rs_.readlines():
            tokens = line.split()
            chain = tokens[2].lower()

            rules.setdefault(chain, {})
            rule_counts.setdefault(chain, 1)

            if tokens[1] == '-P':
                default_rules[chain] = line.rstrip()
            else:
                rules[chain][rule_counts[chain]] = line.rstrip()

            rule_counts[chain] += 1

    for chain in default_rules:
        rules[chain][rule_counts[chain]] = default_rules[chain]


    original_rules = json.load(open('mappings.json'))['forward_filter_mappings']
    original_rules = {
        'original' : {int(k):v for k, v in list(original_rules['original'].items())},
        'expanded' : {int(k):v for k, v in list(original_rules['expanded'].items())}
    }

    shadowed_rules = {}
    for shadowed_id, shadowing_id in list(shadowed_ids.items()):
        original_shadowed_rule = original_rules['original'][shadowed_id]
        expanded_shadowed_rules = original_rules['expanded'][original_rules['original'][shadowed_id]]
        original_shadowing_rule = original_rules['original'][shadowing_id]
        expanded_shadowing_rules = original_rules['expanded'][original_rules['original'][shadowing_id]]

        # cases:
        # 1. single original shadowed rule, single expanded shadowing rule
        # 2. single original shadowed rule, multiple expanded shadowing rules
        # 3. multiple expanded shadowed rules, single expanded shadowing rule
        # 4. multiple expanded shadowed rules, multiple expanded shadowing rules

#        print "\nshadowed", shadowed_id, original_shadowed_rule, expanded_shadowed_rules
#        print "shadowing", shadowing_id, original_shadowing_rule, expanded_shadowing_rules
#        print "related shadowed", [shadowed_ids[r] for r in expanded_shadowed_rules]

#        print [shadowed_ids[r] in expanded_shadowing_rules for r in expanded_shadowed_rules]

        if all([shadowed_ids[r] in expanded_shadowing_rules for r in expanded_shadowed_rules]):
            shadowed_rules[original_shadowed_rule] = original_shadowing_rule
#            print " -> fully shadowed"
#        else:
#            print " -> partly shadowed"


    print(("  Shadowed Rules (%d):" % len(shadowed_rules)))
    for shadowed_rule, shadowing_rule in sorted(shadowed_rules.items()):
        print(("    %d: %s" % (shadowed_rule, rules['forward'][shadowed_rule])))
#        print "      by %d: %s" % (shadowing_rule, rules['forward'][shadowing_rule])

#    print rule_counts
#    print rules['forward'].keys()
#    print shadowed_ids

if __name__ == '__main__':
    _main(sys.argv[1:])
