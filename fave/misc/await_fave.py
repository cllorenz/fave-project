#/usr/bin/env python2

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

""" This module waits until FaVe operations are finished.
"""

import sys
import getopt

from filelock import SoftFileLock
from util.print_util import eprint


def _print_help():
    eprint(
        "usage: python2 " + sys.argv[0] + " [-h]" + " [-d <path>]",
        "\t-h - this help text",
        "\t-d <path> - path to a net_plumber dump",
        sep="\n"
    )




def main(argv):
    """ Main method.
    """

    try:
        only_opts = lambda opts, args: opts
        opts = only_opts(*getopt.getopt(argv, "hd:"))
    except getopt.GetoptError as err:
        eprint("error while fetching arguments: %s" % err)
        _print_help()
        sys.exit(1)

    dump = "np_dump"

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-d':
            dump = arg

    with SoftFileLock("%s/.lock" % dump, timeout=-1):
        pass

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
