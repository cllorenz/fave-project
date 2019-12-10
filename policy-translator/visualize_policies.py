#!/usr/bin/env python2

import sys
import os
import graphviz
from graphviz import Digraph

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print "no file to visualize. quit."
        sys.exit(1)
    elif not os.path.isfile(sys.argv[1]):
        print "not a file: %s. quit." % sys.argv[1]
        sys.exit(2)
    elif not os.path.isfile(sys.argv[2]):
        print "not a file: %s. quit." % sys.argv[2]
        sys.exit(2)

    roles_and_services = sys.argv[1]
    policies = sys.argv[2]

    roles = {'Internet' : []}
    with open(roles_and_services, 'r') as f:
        for line in f.read().split('\n'):
            if line.startswith('#'): continue

            token = line.lstrip().split(' ')
            if len(token) == 3 and token[0] == 'def' and token[1] in ['role', 'abstract_role']:
                roles.setdefault(token[2], [])
                current_role = token[2]
            elif len(token) == 2 and token[0] == 'includes':
                roles[current_role].append(token[1])

    default = 'deny'
    reach = {}
    with open(policies, 'r') as f:
        for line in f.read().split('\n'):
            if line.startswith('#'): continue

            token = line.lstrip().split(' ')
            if len(token) == 3 and token[0] == 'describe':
                default = token[2].rstrip(')')
            elif len(token) == 3 and token[1] in ['--->', '<-->', '<->>']:
                src, operator, dst = token
                reach.setdefault(src, [])
                reach[src].append((operator, dst))


    g = Digraph(format='svg')

#    seen = []
#    for role in roles:
#        if role not in seen:
#            g.node(role, shape='rectangle')
#            seen.append(role)
#
#        if roles[role]:
#            for subrole in roles[role]:
#                if subrole not in seen:
#                    g.node(subrole, shape='rectangle')
#                    seen.append(subrole)
#
#                g.edge(role, subrole, arrowtail='diamond')

    seen = []
    sub_edges = []
    for src in reach:
        if src not in seen:
            g.node(src, shape='rectangle')
            seen.append(src)

        for operator, dst in reach[src]:
            if dst not in seen:
                g.node(dst, shape='rectangle')
                seen.append(dst)

            g.edge(src, dst, dir='both', arrowhead='openopen', arrowtail='open', color='red')

            for subrole in [s for s in roles[src] if s in seen and (src, s) not in sub_edges]:
                g.edge(src, subrole, dir='both', arrowhead='open', arrowtail='odiamond')
                sub_edges.append((src, subrole))

            for subrole in [s for s in roles[dst] if s in seen and (dst, s) not in sub_edges]:
                g.edge(dst, subrole, dir='both', arrowhead='open', arrowtail='odiamond')
                sub_edges.append((dst, subrole))

    g.render('policies', cleanup=True)
    os.popen('inkscape --export-pdf=policies.pdf policies.svg')
