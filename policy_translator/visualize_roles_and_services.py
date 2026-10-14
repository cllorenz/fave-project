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

""" Draws an FPL inventory: roles, the groups that include them, and the
services they offer. Reads FPL through `PolicyBuilder`, the translator's own
parser, so it accepts what the translator accepts -- `def` or `describe`,
any whitespace, services without a port. It once had a tokenizer of its
own that read only `def` blocks and required a port (TODO item 53).

Usage: visualize_roles_and_services.py INVENTORY
Writes roles_and_services.svg (and a PDF through inkscape).
"""

import sys
import os
from graphviz import Digraph

from policy import Policy, Superrole
from policy_builder import PolicyBuilder


def roles_and_services_graph(inventory: str) -> Digraph:
    """ The inventory `inventory` (FPL text) as a graph. """
    # With FPL's built-in `Internet` role, which inventories may include.
    policy = Policy()
    PolicyBuilder.build_roles_and_services(inventory, policy)

    g = Digraph(format='svg')
    for name in policy.roles:
        g.node(name, shape='rectangle')
    for name, role in policy.roles.items():
        if isinstance(role, Superrole):
            for member in role.subroles:
                g.edge(name, member, dir='both', arrowhead='open', arrowtail='odiamond')

    for name, service in policy.services.items():
        attributes = service.attributes
        label = "%s,\nproto: %s" % (name, attributes.get('protocol', '-'))
        if 'port' in attributes:
            label += ",\nport: %s" % attributes['port']
        g.node(name, label=label)

    for name, role in policy.roles.items():
        if not isinstance(role, Superrole):
            for offered in role.services:
                g.edge(name, offered, arrowhead='open', style='dashed')
    return g


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("no file to visualize. quit.")
        sys.exit(1)
    elif not os.path.isfile(sys.argv[1]):
        print("not a file: %s. quit." % sys.argv[1])
        sys.exit(2)

    with open(sys.argv[1], 'r') as f:
        graph = roles_and_services_graph(f.read())
    graph.render('roles_and_services', cleanup=True)
    os.popen('inkscape --export-pdf=roles_and_services.pdf roles_and_services.svg')
