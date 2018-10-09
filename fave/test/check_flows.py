#/usr/bin/env python2

""" This module provides functionality to check FaVe dumps for flow conformity.
"""

import sys
import getopt
import json
import pyparsing as pp

from util.print_util import eprint


def check_tree(flow, tree, depth=0):
    """ Checks whether a specified flow equals a branch in a flow tree.

    Keyword arguments:
    flow -- a flow specification to be checked
    tree -- a flow tree
    """

    # if the end of the flow specification has been reached
    if not flow:
        return True

    # if a tree leaf has been reached but flow specification is not done yet
    elif not tree:
        return False

    # check START specification
    elif flow[0][0] == 'START':
        # check whether the actual node and the rest of the specification matches
        # the tree
        return tree["node"] in flow[0][1] and check_tree(flow[1:], tree, depth+1)

    # check EX specification with existing subtrees
    elif flow[0][0] == 'EX' and "children" in tree:
        for subtree in tree["children"]:
            # check whether subtree node and the rest of the specification matches
            # the subtree
            if subtree["node"] in flow[0][1] and check_tree(flow[1:], subtree, depth+1):
                return True

    # check EX specification for leaf
    elif flow[0][0] == 'EX' and "children" not in tree:
        return False

    # check EF with existing subtree
    elif flow[0][0] == 'EF' and "children" in tree:
        for subtree in tree["children"]:
            # check whether subtree node does not match but the specification matches
            # the subtree
            if subtree["node"] not in flow[0][1] and check_tree(flow, subtree, depth+1):
                return True
            # check whether subtree node matches and the rest of the specification
            # matches the subtree
            elif subtree["node"] in flow[0][1] and check_tree(flow[1:], subtree, depth+1):
                return True

        return False

    # check EF specification for leaf
    elif flow[0][0] == 'EF' and "children" not in tree:
        # check whether leaf satisfies specification and rest of specification is
        # empty
        return tree["node"] in flow[0][1] and not flow[1:]

    return False


def check_flow(flow_spec, flow_tree, inv_fave):
    """ Checks if a flow tree satisfies a flow path specification.

    Keyword arguments:
    flow_spec -- path to be checked
    flow_tree -- flow tree to be matched
    inv_fave -- inverse fave mappings
    """

    nflow = []
    negated = False
    flow_spec_iter = iter(flow_spec)
    for tok in flow_spec_iter:
        if tok in ['(', ')', ' ', '&&']:
            continue
        elif tok == '!':
            negated = True
        elif tok.startswith('s='):
            _, tname = tok.split('=')
            crule = ('START', [inv_fave["generator_to_id"][tname]])
            nflow.append(crule)
        elif tok in ['EX', 'EF']:
            flow_spec_iter.next()
            ttype, tname = flow_spec_iter.next().split('=')
            crules = (
                tok,
                [inv_fave["probe_to_id"][tname]] if ttype == 'p' else \
                inv_fave["table_id_to_rules"][inv_fave["table_to_id"][tname]]
            )
            nflow.append(crules)

        else:
            raise Exception("cannot handle token: %s" % tok)

    return negated != check_tree(nflow, flow_tree)


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


def _parse_flow_spec(flow):
    ident = pp.Combine(
        pp.Word(pp.alphas) + pp.ZeroOrMore(pp.Word(pp.alphanums + "." + "_" + "-"))
    )
    tok_source = pp.Combine(pp.CaselessLiteral("s=") + ident)
    tok_probe = pp.Combine(pp.CaselessLiteral("p=") + ident)
    tok_table = pp.Combine(pp.CaselessLiteral("t=") + ident)
    tok_oper_neg = pp.CaselessLiteral("!")
    tok_oper_and = pp.CaselessLiteral("&&")
    tok_oper_ex = pp.CaselessLiteral("EX")
    tok_oper_ef = pp.CaselessLiteral("EF")
    tok_block_open = pp.CaselessLiteral("(")
    tok_block_close = pp.CaselessLiteral(")")

    expr_atom = tok_source ^ tok_probe ^ tok_table
#    source_test = "s=foo"
#    print source_test, "->", expr_atom.parseString(source_test)
#    probe_test = "p=bar_bla"
#    print probe_test, "->", expr_atom.parseString(probe_test)
#    table_test = "t=baz"
#    print table_test, "->", expr_atom.parseString(table_test)

    expr_temp = tok_oper_ex + pp.White() + expr_atom ^ \
        tok_oper_ef + pp.White() + expr_atom ^ expr_atom
#    ex_test = "EX %s" % table_test
#    print ex_test, "->", expr_temp.parseString(ex_test)
#    ef_test = "EF %s" % probe_test
#    print ef_test, "->", expr_temp.parseString(ef_test)

    expr_par = tok_block_open + expr_temp + tok_block_close ^ expr_temp
#    par_ex_test = "(%s)" % ex_test
#    print par_ex_test, "->", expr_par.parseString(par_ex_test)
#    par_ef_test = "(%s)" % ef_test
#    print par_ef_test, "->", expr_par.parseString(par_ef_test)
#    par_atom_test = source_test
#    print par_atom_test, "->", expr_par.parseString(par_atom_test)

    expr_and = expr_par + pp.White() + tok_oper_and + pp.White() + expr_par ^ expr_par
#    and_test = "%s && %s" % (par_ex_test, par_ef_test)
#    print and_test, "->", expr_and.parseString(and_test)

    expr = pp.ZeroOrMore(tok_oper_neg + pp.White()) + expr_and + pp.ZeroOrMore(pp.White() + tok_oper_and + pp.White() + expr_and) ^ expr_and
#    expr_test = "%s && %s" % (par_atom_test, and_test)
#    print expr_test, "->", expr.parseString(expr_test)

#    print flow, "->", expr.parseString(flow, parseAll=True)

    return expr.parseString(flow)


def _check_flow_trees(flow_spec, flow_trees, inv_fave):
    for flow_tree in flow_trees:
        if check_flow(flow_spec, flow_tree, inv_fave):
            return True

    return False


def _print_help():
    eprint(
        "usage: python2 " + sys.argv[0] + " [-h]" + " [-d <path>]"  " -c <path specs>",
        "\t-h - this help text",
        "\t-d <path> - path to a net_plumber dump",
        "\t-c <path specs> - specifications of paths divided by semicola",
        sep="\n"
    )


def main(argv):
    """ Main method.
    """

    try:
        only_opts = lambda opts, args: opts
        opts = only_opts(*getopt.getopt(argv, "hd:c:"))
    except getopt.GetoptError as err:
        eprint("error while fetching arguments: %s" % err)
        _print_help()
        sys.exit(1)

    dump = "np_dump"
    flow_specs = []

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-d':
            dump = arg
        elif opt == '-c':
            flow_specs = [_parse_flow_spec(flow) for flow in arg.split(';')]

    if not flow_specs:
        eprint("missing flow check specifications")
        _print_help()
        sys.exit(2)

    inv_fave = _get_inverse_fave(dump)
    flow_trees = _get_flow_trees(dump)

    failed = []
    for flow_spec in flow_specs:
        if not _check_flow_trees(flow_spec, flow_trees, inv_fave):
            failed.append(' '.join([e for e in flow_spec if e != ' ']))

    print (
        "success: all checked flows matched"
    ) if not failed else (
        "failure: some flows mismatched:\n\t%s" % '\n\t'.join(failed)
    )
    return 0 if not failed else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
