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

""" This module provides functionality to check FaVe dumps for flow conformity.
"""

import sys
import getopt
import json
import pyparsing as pp
import csv
import cachetools
import time

from openflow.switch import SwitchRuleField
from ip6np.ip6np_util import field_value_to_bitvector
from netplumber.vector import Vector, get_field_from_vector
from netplumber.vector import HeaderSpace

from filelock import SoftFileLock

from util.print_util import eprint

measurements = []

def check_field(flow, field, value, mapping):
    hs = HeaderSpace.from_str(flow)
    vector = get_field_from_vector(mapping, hs.hs_list[0], field)
    rule_field = SwitchRuleField(field, value)
    return vector == field_value_to_bitvector(rule_field).vector


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

    # check flow field
    elif flow[0][0] == 'FLOW':
        return check_field(tree["flow"], flow[0][1], flow[0][2], flow[0][3])

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
            try:
                crule = ('START', [inv_fave["generator_to_id"][tname]])
            except KeyError as ke:
                eprint("skip unknown generator: %s" % ke.message)
                raise
            nflow.append(crule)
        elif tok in ['EX', 'EF']:
            flow_spec_iter.next()
            ttype, tname = flow_spec_iter.next().split('=')
            try:
                crules = (
                    tok,
                    [inv_fave["probe_to_id"][tname]] if ttype == 'p' else \
                    inv_fave["table_id_to_rules"].get(inv_fave["table_to_id"][tname], [])
                )
            except KeyError as ke:
                eprint("skip unknown entity: %s" % ke.message)
                raise
            nflow.append(crules)

        elif tok.startswith('f='):
            _, fv = tok.split('=')
            field, value = fv.split(':')
            frule = ('FLOW', field, value, inv_fave['mapping'])
            nflow.append(frule)


        else:
            raise Exception("cannot handle token: %s" % tok)

    return negated != check_tree(nflow, flow_tree)


def _get_inverse_fave(dump):
    fave = json.load(open(dump+"/fave.json", "r"))

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
        "probe_to_id" : dict([(v, int(k)) for k, v in fave["id_to_probe"].items()]),
        "mapping" : fave["mapping"]
    }


def _get_flow_trees(dump):
    return json.load(open(dump+"/flow_trees.json"), "r")["flows"]


def _get_flow_tree(dump, cache):
    if dump in cache:
        return cache[dump]
    else:
        j = json.load(open(dump, "r"))["flows"]
        cache.update({dump : j})
        return j


def _get_parser():
    value = pp.OneOrMore(pp.Word(pp.alphanums + "." + "_" + "-"))
    ident = pp.Combine(
        pp.Word(pp.alphas) + pp.ZeroOrMore(pp.Word(pp.alphanums + "." + "_" + "-"))
    )
    tok_source = pp.Combine(pp.CaselessLiteral("s=") + ident)
    tok_probe = pp.Combine(pp.CaselessLiteral("p=") + ident)
    tok_table = pp.Combine(pp.CaselessLiteral("t=") + ident)
    tok_field = pp.Combine(pp.CaselessLiteral("f=") + ident + pp.CaselessLiteral(":") + value)
    tok_oper_neg = pp.CaselessLiteral("!")
    tok_oper_and = pp.CaselessLiteral("&&")
    tok_oper_ex = pp.CaselessLiteral("EX")
    tok_oper_ef = pp.CaselessLiteral("EF")
    tok_block_open = pp.CaselessLiteral("(")
    tok_block_close = pp.CaselessLiteral(")")

    expr_atom = tok_source ^ tok_probe ^ tok_table ^ tok_field
#    source_test = "s=foo"
#    print source_test, "->", expr_atom.parseString(source_test)
#    probe_test = "p=bar_bla"
#    print probe_test, "->", expr_atom.parseString(probe_test)
#    table_test = "t=baz"
#    print table_test, "->", expr_atom.parseString(table_test)
#    field_test = "f=foo:0"
#    print field_test, "->", expr_atom.parseString(field_test)

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

    return expr


def _parse_flow_spec(flow, parser):
    return parser.parseString(flow)


def _get_source(flow_spec):
    for token in flow_spec:
        if token.startswith("s="): return token[2:]

    raise Exception("cannot find source in flow spec: %s" % flow_spec)


def _is_leaf(flow_tree):
    return 'children' not in flow_tree


def _get_flow_tree_leaves(flow_tree):
    if _is_leaf(flow_tree):
        return {flow_tree['node'] : flow_tree}

    leaves = {}
    for child in flow_tree['children']:
        leaves.update(_get_flow_tree_leaves(child))

    return leaves


def _check_flow_trees(flow_spec, flow_trees, inv_fave, cache):
    source = _get_source(flow_spec)
    fts = _get_flow_tree(flow_trees[source], cache)

    t_start = time.time()

    res = False
    for flow_tree in fts:
        if check_flow(flow_spec, flow_tree, inv_fave):
            res = True
            break

    t_end = time.time()
    print "checked flow in %s ms" % ((t_end - t_start) * 1000.0)
    measurements.append((t_end - t_start) * 1000.0)

    return res


def _build_ordered_flow_specs(flow_specs):
    ordered_flow_specs = {}
    for flow_spec in flow_specs:
        neg = False
        src = None
        dst = None
        fld = None
        for token in flow_spec:
            if token.startswith('!'):
                neg = True
            elif token.startswith('s='):
                src = token[2:]
            elif token.startswith('p='):
                dst = token[2:]
            elif token.startswith('f='):
                fld = token[2:]

        if src and dst:
            ordered_flow_specs.setdefault(src, [])
            ordered_flow_specs[src].append((dst, neg, fld, flow_spec))

    return ordered_flow_specs


def _print_help():
    eprint(
        "usage: python2 " + sys.argv[0] + " [-h]" + " [-d <path>]"  " -c <path specs>",
        "\t-h - this help text",
        "\t-d <path> - path to a net_plumber dump",
        "\t-c <path specs> - specifications of paths divided by semicola",
        sep="\n"
    )


def _update_reachability_matrix(matrix, spec, success, exception=False):
    if spec[0] == '!':
        spec = spec[2:]
        positive = False
    else:
        positive = True

    source = spec[0][9:] #skip s=source.
    source = source[:source.rfind('.ifi')] if source != 'Internet' else source
    dest = spec[-2][8:] if spec[-1].startswith('f=') else spec[-1][8:] # skip p=probe.
    dest = dest[:dest.rfind('.ifi')] if dest != 'Internet' else dest

    if exception:
        symbol = '_'
    else:
        symbol = ('X' if len(spec) != 3 else '(X)') if not success ^ positive else ''

    matrix.setdefault(source, {'' : source})
    matrix[source][dest] = symbol



def main(argv):
    """ Main method.
    """

    try:
        only_opts = lambda opts, args: opts
        opts = only_opts(*getopt.getopt(argv, "hbd:c:r"))
    except getopt.GetoptError as err:
        eprint("error while fetching arguments: %s" % err)
        _print_help()
        sys.exit(1)

    dump = "np_dump"
    flow_specs = []
    dump_matrix = False
    broad = False

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-b':
            broad = True
        elif opt == '-d':
            dump = arg
        elif opt == '-c':
            parser = _get_parser()
            flow_specs = [_parse_flow_spec(flow, parser) for flow in arg.split(';') if flow]
        elif opt == '-r':
            dump_matrix = True

    if not flow_specs:
        eprint("missing flow check specifications")
        _print_help()
        return 2

    with SoftFileLock("%s/.lock" % dump, timeout=-1):
        inv_fave = _get_inverse_fave(dump)
        #flow_trees = _get_flow_trees(dump)
        flow_trees = {
            k : "%s/%s.flow_tree.json" % (dump, v) for k, v in inv_fave["generator_to_id"].iteritems()
        }

    failed = []
    reach = {'' : {'' : ''}}
    cache = cachetools.LRUCache(10)
    if broad:
        ordered_flow_specs = _build_ordered_flow_specs(flow_specs)

        mapping = inv_fave['mapping']

        for src, specs in ordered_flow_specs.iteritems():
            flow_tree = _get_flow_tree(flow_trees[src], cache)[0]

            t_start = time.time()

            flow_tree_leaves = _get_flow_tree_leaves(flow_tree)

            for dst, neg, fld, spec in specs:

                if not inv_fave['probe_to_id'][dst] in flow_tree_leaves:
                    if not neg:
                        failed.append(' '.join([e for e in spec if e != ' ']))
                    continue

                leaf = flow_tree_leaves[inv_fave['probe_to_id'][dst]]
                res = False

                if fld:
                    field, value = fld.split(':')
                    res = check_field(leaf['flow'], field, value, mapping)

                if res and neg:
                    failed.append(' '.join([e for e in spec if e != ' ']))

            t_end = time.time()
            print "checked flow tree in %s ms" % ((t_end - t_start) * 1000.0)
            measurements.append((t_end - t_start) * 1000.0)

    else:
        for no, flow_spec in enumerate(flow_specs, start=1):
            try:
                successful = _check_flow_trees(flow_spec, flow_trees, inv_fave, cache)
            except KeyError as ke:
                _update_reachability_matrix(reach, flow_spec, False, exception=True)
                continue

            if not successful:
                failed.append(' '.join([e for e in flow_spec if e != ' ']))
                _update_reachability_matrix(reach, flow_spec, False)
            else:
                _update_reachability_matrix(reach, flow_spec, True)

            if no % 1000 == 0:
                print "  checked %s flows" % no

    print (
        "success: all %s checked flows matched" % len(flow_specs)
    ) if not failed else (
        "failure: the following flows mismatched:\n\t%s\nwhich is %s of %s." % (
            '\n\t'.join(failed), len(failed), len(flow_specs)
        )
    )

    print "runtimes:\n\ttotal: %s ms\n\tmean: %s ms\n\tmedian: %s ms\n\tmin: %s ms\n\tmax: %s ms" % (
        sum(measurements),
        sum(measurements)/len(measurements),
        sorted(measurements)[len(measurements)/2],
        min(measurements),
        max(measurements)
    )

    if dump_matrix:
        with open(dump+'/reach.csv', 'w') as csvf:
            header = sorted(reach)
            csv_writer = csv.DictWriter(csvf, header)
            csv_writer.writeheader()

            for source in header:
                csv_writer.writerow(reach[source])

    return 0 if not failed else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
