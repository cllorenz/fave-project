#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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

""" Shadowing benchmark.
"""


import os
import sys

RULESET = "bench/wl_shadow/rules.ipt"
INVENTORY = "bench/wl_shadow/inventory.txt"
POLICY = "bench/wl_shadow/policy.txt"
INTERFACES = "bench/wl_shadow/interfaces.json"

def main(_argv):
    """ main
    """

    use_unix = True
    verbose = False

    os.system("python2 bench/wl_generic_fw/benchmark.py -6 -n -r %s -i %s -p %s -m %s %s %s" % (
        RULESET,
        INVENTORY,
        POLICY,
        INTERFACES,
        "-u" if use_unix else "",
        "-v" if verbose else ""
    ))

if __name__ == '__main__':
    main(sys.argv[1:])
