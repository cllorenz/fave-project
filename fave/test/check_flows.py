#/usr/bin/env python2

""" This module provides functionality to check FaVe dumps for flow conformity.
"""

import sys
import json

DUMP = sys.argv[1]
CFLOWS = sys.argv[2]

def check_tree(cflow, tree, d=0):
    # if the end of the suspect flow has been reached
    if not cflow:
#        print "  "*d, "reached eof"
        return True

    # if a tree leaf has been reached but suspect flow is not done yet
    if not tree:
#        print "  "*d, "reached eot"
        return False

    # if the tree node and the suspect flow mismatch
    elif tree["node"] not in cflow[0]:
#        print "  "*d, "unmatching nodes: %s not in %s" % (tree["node"], cflow[0])
        return False

    # if the tree has no children to try
    elif not "children" in tree:
        if  not cflow[1:]:
#            print "  "*d, "reached eof and eot"
            return True
        else:
#            print "  "*d, "reached eot but not eof"
            return False

    # if the tree's children are empty (should never happen)
    elif not tree["children"]:
#        print "  "*d, "reached eot"
        return False

    # otherwise try the next node with a subtree
    else:
        for subtree in tree["children"]:
#            print "  "*d, "try subtree %s for %s" % (subtree["node"], cflow[1:])
            if check_tree(cflow[1:], subtree, d+1):
#                print "  "*d, "subtree %s matched flow %s" % (subtree["node"], cflow[1:])
                return True
#        print "  "*d, "no subtree matched flow"
        return False


def check_flow(cflow, pflows, inv_fave):
    """ Checks flows .

    Keyword arguments:
    cflow -- path to be checked
    pflow -- flow tree
    inv_fave -- inverse fave mappings
    """

    nflow = []
    for node in cflow:
        if 't=' in node:
            _, table = node.split('=')
            crules = inv_fave["table_id_to_rules"][inv_fave["table_to_id"][table]]
            nflow.append(crules)
        elif node in inv_fave["generator_to_id"]:
            crule = inv_fave["generator_to_id"][node]
            nflow.append([crule])
        elif node in inv_fave["probe_to_id"]:
            crule = inv_fave["probe_to_id"][node]
            nflow.append([crule])
        else:
            raise Exception("no such generator or probe: %s" % node)

#    print "\nnflow:", nflow
#    print "pflow:", pflow

    return check_tree(nflow, pflow)


with open(DUMP+"/fave.json", "r") as ifile:
    fave = json.loads(ifile.read())

    id_to_rule = fave["id_to_rule"]
    table_id_to_rules = {}
    for rid in id_to_rule:
        tid = id_to_rule[rid]
        if tid in table_id_to_rules:
            table_id_to_rules[tid].append(int(rid))
        else:
            table_id_to_rules[tid] = [int(rid)]

    inv_fave = {
        "table_to_id" : dict([(v, int(k)) for k, v in fave["id_to_table"].items()]),
        "table_id_to_rules" : table_id_to_rules,
        "generator_to_id" : dict([(v, int(k)) for k, v in fave["id_to_generator"].items()]),
        "probe_to_id" : dict([(v, int(k)) for k, v in fave["id_to_probe"].items()])
    }

with open(DUMP+"/flow_trees.json") as ifile:
    pflows = json.loads(ifile.read())["flows"]

CFLOWS = [json.loads(flow) for flow in CFLOWS.split(';')]

all_flows = True
any_flow = False
for cflow in CFLOWS:
    for pflow in pflows:

        if check_flow(cflow, pflow, inv_fave):
            any_flow = True
            break

    all_flows = all_flows and any_flow

#    if any_flow:
#        print " true",
#    else:
#        print " false",

    any_flow = False

print "all checked flows matched" if all_flows else "some checked flow mismatched"
