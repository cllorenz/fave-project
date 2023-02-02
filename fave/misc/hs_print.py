#!/usr/bin/env python3

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

""" This module provides simple utilities to print a header space object from a
    NetPlumber dump.
"""

import sys
import json

from netplumber.vector import HeaderSpace

def print_help():
    """ Prints the usage message.
    """
    print("usage: python3 hs_print <fave.json> <hs.txt>")


if __name__ == '__main__':
    ARGV = sys.argv[1:]

    if len(ARGV) != 2:
        print_help()
        sys.exit(1)

    MAPPING = json.load(open(ARGV[0], 'r'))['mapping']

    with open(ARGV[1], 'r') as f:
        HS_STR = f.read()

    HSP = HeaderSpace.from_str(HS_STR)

    HSP.pprint(MAPPING)
