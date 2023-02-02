#!/usr/bin/env python2

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

import sys
import os
import graphviz
from graphviz import Digraph

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("no file to visualize. quit.")
        sys.exit(1)
    elif not os.path.isfile(sys.argv[1]):
        print("not a file: %s. quit." % sys.argv[1])
        sys.exit(2)

    roles_and_services = sys.argv[1]

    roles = {}
    services = {}
    offers = {}
    with open(roles_and_services, 'r') as f:
        current_role = ''
        current_service = ''
        for line in f.read().split('\n'):
            if line.startswith('#'): continue

            token = line.lstrip().split(' ')
            if len(token) == 3 and token[0] == 'def' and token[1] in ['role', 'abstract_role']:
                roles.setdefault(token[2], [])
                current_role = token[2]
            elif len(token) == 2 and token[0] == 'includes':
                roles[current_role].append(token[1])
            elif len(token) == 3 and token[0] == 'def' and token[1] == 'service':
                services.setdefault(token[2], {})
                current_service = token[2]
            elif len(token) == 3 and token[0] in ['protocol', 'port']:
                services[current_service][token[0]] = token[2]
            elif len(token) == 2 and token[0] == 'offers':
                offers.setdefault(current_role, [])
                offers[current_role].append(token[1])

    g = Digraph(format='svg')

    seen = []
    for role in roles:
        if role not in seen:
            g.node(role, shape='rectangle')
            seen.append(role)

        if roles[role]:
            for subrole in roles[role]:
                if subrole not in seen:
                    g.node(subrole, shape='rectangle')
                    seen.append(role)

                g.edge(role, subrole, dir='both', arrowhead='open', arrowtail='odiamond')

    seen = []
    for service in services:
        if service not in seen:
            label = "%s,\nproto: %s,\nport: %s" % (service, services[service]['protocol'], services[service]['port'])
            g.node(service, label=label)
            seen.append(service)

    seen = []
    for offer in offers:
        for service in offers[offer]:
            g.edge(offer, service, arrowhead='open', style='dashed')

    g.render('roles_and_services', cleanup=True)
    os.popen('inkscape --export-pdf=roles_and_services.pdf roles_and_services.svg')
