#!/usr/bin/env python3

#import getopt
import logging
import sys
import argparse
import pprint

from copy import deepcopy as dc
from functools import reduce

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))


class ArgumentParserError(Exception): pass

class ThrowingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentParserError(message)


def _get_chain_from_rule(rule):
    for opt, arg in rule:
        if opt == "append":
            return arg[0]

    LOGGER.error("no chain in rule: %s", rule)
    raise Exception("no chain in rule: " + str(rule))


def _get_action_from_rule(rule):
    for opt, arg in rule:
        if opt == "jump":
            return arg[0]

    return 'EMPTY'

    #LOGGER.info("no action in rule %s", rule)
    #raise Exception("no action in rule: " + str(rule))


def _get_chain_from_rule(rule):
    for opt, arg in rule:
        if opt == 'append':
            return arg[0]


def _get_body_from_rule(rule):
    return [(opt, arg) for opt, arg in rule if opt not in ['append', 'jump']]

def _get_negated_from_rule(rule):
    return [arg[0] for opt, arg in rule if opt == 'negated']

# from: Diekmann et al., Semantics-Preserving Simplification of Real-World Firewall Rule Sets, 2015.
# type: ()x[[()]] -> [[()]]
def _add_negated_match(match, rules):
    if not match:
        return []

    if len(match) == 1:
        return [_add_match([('negated', [match[0][0]]), match[0]], rules)]

    else:
        concat = lambda x, y: x + y
        return reduce(
            concat,
            [_add_match([('negated', [m[0]]), m], rules) for m in match]
        )


# from: Diekmann et al., Semantics-Preserving Simplification of Real-World Firewall Rule Sets, 2015.
# type: [()]x[[()]] -> [[()]]
def _add_match(match, rules):
    if isinstance(match, tuple):
        return [[match] + rule for rule in rules]

    elif isinstance(match, list):
        return [match + rule for rule in rules]

    else:
        LOGGER.error("could not add match %s to rules %s", match, rules)
        return []


# from: Diekmann et al., Semantics-Preserving Simplification of Real-World Firewall Rule Sets, 2015.
# type: [[()]] -> [[()]]
def _flatten_chain(chain):
    if not chain:
        return []

    action = _get_action_from_rule(chain[0])
    rule_body = _get_body_from_rule(chain[0])
    if action == "RETURN":
        processed_chain = _flatten_chain(chain[1:])
        return _add_negated_match(rule_body, processed_chain)

    else:
        return [rule_body + [('jump', [action])]] + _flatten_chain(chain[1:])


# from: Diekmann et al., Semantics-Preserving Simplification of Real-World Firewall Rule Sets, 2015.
# type: [[()]]x{[[()]]} -> [[()]]
def _flatten_call(chain, chain_name, custom_chains):
    if not chain:
        return []

    action = _get_action_from_rule(chain[0])
    if action not in ["ACCEPT", "DROP", "REJECT", "LOG", "EMPTY"]:
        rule_body = _get_body_from_rule(chain[0])
        processed_chain = _flatten_chain(custom_chains[action])
        flattened_rest = _flatten_call(chain[1:], chain_name, custom_chains)
        return _add_match([('append', [chain_name])] + rule_body, processed_chain) + flattened_rest

    else:
        return [chain[0]] + _flatten_call(chain[1:], chain_name, custom_chains)


def _expand_rule_with_chain(rule, chain):
    rule_body = _get_body_from_rule(rule)
    res = []
    for chain_rule in chain:
        cr = [(opt, arg) for opt, arg in chain_rule if opt is not "append"]
        res.append(rule_body + cr)

    return res


def _normalize_rule(rule, custom_chains, seen=[]):
    try:
        action = _get_action_from_rule(rule)
    except:
        LOGGER.warning("no action")
        return []
    if action in ["ACCEPT", "DROP", "REJECT"]:
        return [rule]
    elif action == "LOG":
        return []
    elif action == "RETURN":
        return []
    elif action in seen:
        LOGGER.warning(
            "loop prevention: action %s already seen in %s", action, seen
        )
        return []
    else:
        exp_rules = _expand_rule_with_chain(rule, custom_chains[action])
        concat = lambda x, y: x + y
        return reduce(
            concat,
            [_normalize_rule(r, custom_chains, seen=seen+[action]) for r in exp_rules]
        )

if __name__ == '__main__':
    orig = "iptables-save-2016-06-27_16-29-01"
    #orig = "iptables-save-foo"
    ruleset = "pgf-ruleset"

    final_chains = {
        "PRE_ROUTING" : [],
        "POST_ROUTING" : [],
        "INPUT" : [],
        "OUTPUT" : [],
        "FORWARD" : []
    }

    with open(orig, 'r') as orig:
        rules = orig.read().splitlines()

        parser = ThrowingArgumentParser(add_help=False)
        parser.add_argument('-A', '--append', nargs=1)
        parser.add_argument('-i', '--in-interface', nargs=1)
        parser.add_argument('-o', '--out-interface', nargs=1)
        parser.add_argument('-s', '--source', nargs=1)
        parser.add_argument('-d', '--destination', nargs=1)
        parser.add_argument('-p', '--protocol', nargs=1)
        parser.add_argument('-m', '--match', nargs=1)
        parser.add_argument('-j', '--jump', nargs=1)
        parser.add_argument('--sport', nargs=1)
        parser.add_argument('--dport', nargs=1)
        parser.add_argument('--mac-source', nargs=1)
        parser.add_argument('--state', nargs=1)
        parser.add_argument('--tcp-flags', nargs=2)
        parser.add_argument('--dports', nargs=1)
        parser.add_argument('--limit', nargs=1)
        parser.add_argument('--reject-with', nargs=1)
        parser.add_argument('--log-prefix', nargs=1)
        parser.add_argument('--hitcount', nargs=1) # module: recent, narrows lookups by counter
        parser.add_argument('--update', action='store_const', const=[]) # module: recent, updates a list item
        parser.add_argument('--seconds', nargs=1) # module: recent, narrows lookups by time
        parser.add_argument('--name', nargs=1) # module: recent, specifies a list name
        parser.add_argument('--rsource', action='store_const', const=[]) # module: recent, applies an action using a src address
        parser.add_argument('--set', action='store_const', const=[]) # module: recent, adds/update a source address to/in list
        parser.add_argument('--to-source', nargs=1)

        parsed_rules = []

        for rule in rules:
            try:
                ns = parser.parse_args(rule.split(' '))
            except ArgumentParserError:
                continue

            parsed_rules.append([(x, y) for x, y in vars(ns).items() if y is not None])

        custom_chains = {}
        standard_chains = {
            "PRE_ROUTING" : [],
            "POST_ROUTING" : [],
            "INPUT" : [],
            "OUTPUT" : [],
            "FORWARD" : []
        }

        for rule in parsed_rules:
            chain = _get_chain_from_rule(rule)
            if chain in ["PRE_ROUTING", "POST_ROUTING", "INPUT", "OUTPUT", "FORWARD"]:
                standard_chains[chain].append(rule)
            elif chain not in custom_chains:
                custom_chains[chain] = [rule]
            else:
                custom_chains[chain].append(rule)

        for chain in standard_chains:
            cur_chain = standard_chains[chain]
            while True:
                new_chain = _flatten_call(cur_chain, chain, custom_chains)
                if new_chain == cur_chain:
                    final_chains[chain] = new_chain
                    break
            
                cur_chain = new_chain

            #for rule in standard_chains[chain]:
            #    final_chains[chain].extend(_normalize_rule(rule, custom_chains))

    with open(ruleset, 'w') as ofile:
        ofile.write(
            '\n'.join(["iptables -P %s DROP" % c for c in final_chains]) + '\n'
        )

        for chain in final_chains:
            for rule in final_chains[chain]:
                action = _get_action_from_rule(rule)
                negated = _get_negated_from_rule(rule)
                rule_body = [
                    "%s--%s %s" % (
                        '! ' if opt in negated else '',
                        opt,
                        ' '.join(arg)
                    ) for opt, arg in rule if opt not in ['append', 'jump', 'negated']
                ]

                ofile.write(
                    "iptables -A %s %s -j %s\n" % (chain, ' '.join(rule_body), action)
                )

