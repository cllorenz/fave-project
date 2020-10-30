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

""" This module provides functionality to let FaVe dump its state.
"""

import os
import sys
import getopt
import json

from util.aggregator_utils import connect_to_fave

from util.print_util import eprint
from util.lock_util import PersistentFileLock


def print_help():
    """ Prints usage message to stderr.
    """

    eprint(
        "dump_np -ahfnp -o <dir>",
        "\t-a dump fave aggregator",
        "\t-h print this help and exit",
        "\t-f dump flows",
        "\t-n dump plumbing network (tables, links, rules, policy)",
        "\t-o <dir> output directory (default: np_dump)",
        "\t-p dump pipes",
        "\t-t dump flow trees",
        sep="\n"
    )



def main(argv):
    """ Sends an event to FaVe to dump its state.
    """

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(getopt.getopt(argv, "ahfno:pt"))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    use_fave = False
    use_flows = False
    use_network = False
    use_pipes = False
    use_trees = False

    odir = "np_dump"

    for opt, arg in opts:
        if opt == '-h':
            eprint("usage:")
            print_help()
            sys.exit(0)

        elif opt == '-a':
            use_fave = True

        elif opt == '-f':
            use_flows = True

        elif opt == '-n':
            use_network = True

        elif opt == '-p':
            use_pipes = True

        elif opt == '-o':
            odir = arg

        elif opt == '-t':
            use_trees = True

        else:
            eprint("unknown option: %s, usage:" % opt)
            print_help()
            sys.exit(1)


    fave = connect_to_fave()

    dump = {
        'type':'dump',
        'dir':odir,
        'fave':use_fave,
        'flows':use_flows,
        'network':use_network,
        'pipes':use_pipes,
        'trees':use_trees
    }

    if any([use_fave, use_flows, use_network, use_pipes, use_trees]):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)
        os.system("rm -f %s/.lock" % odir)

    lock = PersistentFileLock("%s/.lock" % odir, timeout=-1)
    lock.acquire()

    fave.sendall(json.dumps(dump))
    fave.close()


if __name__ == '__main__':
    main(sys.argv[1:])
