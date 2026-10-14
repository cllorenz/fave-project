#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

""" Draws an FPL policy: one edge per rule, from the role it grants or
forbids access to the role (and service) it names, and the groups the drawn
roles belong to. Reads FPL through `PolicyBuilder`, the translator's own
parser. It once had a tokenizer of its own that skipped any rule not written
as exactly three space-separated tokens and failed on `Role.Service` targets
(TODO item 53).

A permitting rule (`--->`, `<-->`, `<->>`) is drawn red, a forbidding one
(`--/->`, `<-/->`, `-/->>`) blue and dashed; the edge is labelled with its
operator and, if it names one, its service.

Usage: visualize_policies.py INVENTORY POLICY
Writes policies.svg (and a PDF through inkscape).
"""

import sys
import os
from graphviz import Digraph, nohtml

from policy import Policy, Superrole
from policy_builder import PolicyBuilder


_FORBIDDING = {'--/->', '<-/->', '-/->>'}


def policies_graph(inventory: str, policies: str) -> Digraph:
    """ The policy `policies` over the inventory `inventory` (FPL texts). """
    policy = Policy()
    PolicyBuilder.build(inventory + '\n' + policies, policy)

    g = Digraph(format='svg')
    drawn = []
    for role_from, role_to, service, operator in policy.raw_policies:
        for role in (role_from, role_to):
            if role not in drawn:
                g.node(role, shape='rectangle')
                drawn.append(role)
        # nohtml: an operator such as `<->>` starts with `<` and ends with
        # `>`, which Graphviz would otherwise take for an HTML label.
        label = nohtml(operator + (' %s' % service if service else ''))
        if operator in _FORBIDDING:
            g.edge(role_from, role_to, label=label, color='blue', style='dashed')
        else:
            g.edge(role_from, role_to, label=label, color='red')

    for name in drawn:
        role = policy.roles.get(name)
        if isinstance(role, Superrole):
            for member in role.subroles:
                if member in drawn:
                    g.edge(name, member, dir='both', arrowhead='open',
                           arrowtail='odiamond')
    return g


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("no file to visualize. quit.")
        sys.exit(1)
    elif not os.path.isfile(sys.argv[1]):
        print("not a file: %s. quit." % sys.argv[1])
        sys.exit(2)
    elif not os.path.isfile(sys.argv[2]):
        print("not a file: %s. quit." % sys.argv[2])
        sys.exit(2)

    with open(sys.argv[1], 'r') as f:
        inventory_text = f.read()
    with open(sys.argv[2], 'r') as f:
        policies_text = f.read()
    graph = policies_graph(inventory_text, policies_text)
    graph.render('policies', cleanup=True)
    os.popen('inkscape --export-pdf=policies.pdf policies.svg')
