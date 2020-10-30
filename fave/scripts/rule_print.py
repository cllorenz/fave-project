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
    print "usage: python2 hs_print <fave.json> <hs.txt>"


if __name__ == '__main__':
    argv = sys.argv[1:]

    if len(argv) != 2:
        print_help()
        sys.exit(1)

    fave = json.load(open(argv[0], 'r'))
    mapping = fave['mapping']

    with open(argv[1], 'r') as f:
        rule_str = f.read()

    _at, rno_str, _arrow = rule_str.rstrip().split(' ')

    rno = int(rno_str, 16)
    tno = fave['id_to_rule'][str(rno)]

    table = fave['id_to_table'][str(tno)]

    print "\n@ %s.%s <--\n" % (table, rno & 0xffff)
