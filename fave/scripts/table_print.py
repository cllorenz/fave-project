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

import sys
import json

from netplumber.vector import HeaderSpace

def print_help():
    print "usage: python2 table_print <fave.json> <table.json>"


if __name__ == '__main__':
    argv = sys.argv[1:]

    if len(argv) != 2:
        print_help()
        sys.exit(1)

    fave = json.load(open(argv[0], 'r'))
    mapping = fave['mapping']

    table = json.load(open(argv[1], 'r'))

    print "table:", fave['id_to_table'][str(table['id'])]
    print "ports:", [fave['id_to_port'][str(p)] for p in table['ports']]

    for rule in table['rules']:
        print '\t', 'id:', hex(rule['id'])
        print '\t', 'position:', rule['position']
        print '\t', 'in_ports:', [fave['id_to_port'][str(p)] for p in rule['in_ports']]
        print '\t', 'out_ports:', [fave['id_to_port'][str(p)] for p in rule['out_ports']]
        hs = HeaderSpace.from_str(rule['match'])
        print '\t', 'match:',
        hs.pprint(mapping)
        print ''
