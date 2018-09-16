#/usr/bin/env python2

""" This module provides functionality to check FaVe dumps for flow conformity.
"""

import sys
import getopt
import json

from util.print_util import eprint

def check_tree(flow, tree, depth=0):
    """ Checks whether a specified flow equals a branch in a flow tree.

    Keyword arguments:
    flow -- a flow specification to be checked
    tree -- a flow tree
    """

    # if the end of the suspect flow has been reached
    if not flow:
#        print "  "*depth, "reached eof"
        return True

    # if a tree leaf has been reached but suspect flow is not done yet
    elif not tree:
#        print "  "*depth, "reached eot"
        return False

    # if the tree node and the suspect flow mismatch
    elif tree["node"] not in flow[0]:
#        print "  "*depth, "unmatching nodes: %s not in %s" % (tree["node"], flow[0])
        return False

    # if the tree has no children to try
    elif not "children" in tree:
#        print (
#            "  "*depth, "reached eof and eot"
#        ) if not flow[1:] else (
#            "  "*depth, "reached eot but not eof"
#        )
        return not flow[1:]

    # if the tree's children are empty (should never happen)
    elif not tree["children"]:
#        print "  "*depth, "reached eot"
        return False

    # otherwise try the next node with a subtree
    else:
        for subtree in tree["children"]:
#            print "  "*depth, "try subtree %s for %s" % (subtree["node"], flow[1:])
            if check_tree(flow[1:], subtree, depth+1):
#                print "  "*depth, "subtree %s matched flow %s" % (subtree["node"], flow[1:])
                return True
#        print "  "*depth, "no subtree matched flow"
        return False


def check_flow(cflow, ftree, inv_fave):
    """ Checks if a flow tree satisfies a flow path specification.

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

    return check_tree(nflow, ftree)


def _get_inverse_fave(dump):
    with open(dump+"/fave.json", "r") as ifile:
        fave = json.loads(ifile.read())

        id_to_rule = fave["id_to_rule"]
        table_id_to_rules = {}
        for rid in id_to_rule:
            tid = id_to_rule[rid]
            if tid in table_id_to_rules:
                table_id_to_rules[tid].append(int(rid))
            else:
                table_id_to_rules[tid] = [int(rid)]

        return {
            "table_to_id" : dict([(v, int(k)) for k, v in fave["id_to_table"].items()]),
            "table_id_to_rules" : table_id_to_rules,
            "generator_to_id" : dict([(v, int(k)) for k, v in fave["id_to_generator"].items()]),
            "probe_to_id" : dict([(v, int(k)) for k, v in fave["id_to_probe"].items()])
        }


def _get_flow_trees(dump):
    with open(dump+"/flow_trees.json") as ifile:
        return json.loads(ifile.read())["flows"]


def _print_help():
    eprint(
        "usage: python2 " + sys.argv[0] + " [-h]" + " [-d <path>]"  " -c <path specs>",
        "\t-h - this help text",
        "\t-d <path> - path to a net_plumber dump",
        "\t-c <path specs> - specifications of paths divided by semicola",
        sep="\n"
    )


def _main(argv):
    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "hd:c:"))
    except getopt.GetoptError as err:
        eprint("error while fetching arguments: %s" % err)
        _print_help()
        sys.exit(1)

    dump = "np_dump"
    cflows = ""

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-d':
            dump = arg
        elif opt == '-c':
            cflows = arg

    if not cflows:
        eprint("missing flow check specifications")
        _print_help()
        sys.exit(2)

    cflows = [json.loads(flow) for flow in cflows.split(';')]

    inv_fave = _get_inverse_fave(dump)
    ftrees = _get_flow_trees(dump)

    all_flows = True
    any_tree = False
    failed = []
    for cflow in cflows:
        for ftree in ftrees:

            if check_flow(cflow, ftree, inv_fave):
                any_tree = True
                break

        all_flows = all_flows and any_tree
        if not any_tree:
            failed.append(','.join(cflow))
        any_tree = False

    if all_flows:
        print "success: all checked flows matched"
        return 0
    else:
        print "failure: some flows mismatched:\n\t%s" % ';\n\t'.join(failed)
        return 3


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
