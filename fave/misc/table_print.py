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

""" This module provides simple utilities to print a TABLE from a NetPlumber dump.
"""

import sys
import json

from netplumber.vector import HeaderSpace

def print_help():
    """ Prints the usage message.
    """
    print "usage: python2 TABLE_print <FAVE.json> <TABLE.json>"


if __name__ == '__main__':
    ARGV = sys.argv[1:]

    if len(ARGV) != 2:
        print_help()
        sys.exit(1)

    FAVE = json.load(open(ARGV[0], 'r'))
    MAPPING = FAVE['MAPPING']

    TABLE = json.load(open(ARGV[1], 'r'))

    print "TABLE:", FAVE['id_to_TABLE'][str(TABLE['id'])]
    print "ports:", [FAVE['id_to_port'][str(p)] for p in TABLE['ports']]

    for rule in TABLE['rules']:
        print '\t', 'id:', hex(rule['id'])
        print '\t', 'position:', rule['position']
        print '\t', 'in_ports:', [FAVE['id_to_port'][str(p)] for p in rule['in_ports']]
        print '\t', 'out_ports:', [FAVE['id_to_port'][str(p)] for p in rule['out_ports']]
        hs = HeaderSpace.from_str(rule['match'])
        print '\t', 'match:',
        hs.pprint(MAPPING)
        print ''
