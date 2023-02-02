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

""" This module provides functionality to let FaVe dump its state.
"""

import os
import sys
import getopt
import json

from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
from util.aggregator_utils import connect_to_fave, fave_sendmsg

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
        "\t-s dump simple flow trees",
        "\t-u connect via UNIX domain socket",
        sep="\n"
    )



def main(argv):
    """ Sends an event to FaVe to dump its state.
    """

    try:
        only_opts = lambda opts, _args: opts
        opts = only_opts(*getopt.getopt(argv, "ahfno:pstu"))
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    use_fave = False
    use_flows = False
    use_network = False
    use_pipes = False
    use_trees = False
    keep_simple = False
    use_unix = False

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

        elif opt == '-s':
            use_trees = True
            keep_simple = True

        elif opt == '-u':
            use_unix = True

        else:
            eprint("unknown option: %s, usage:" % opt)
            print_help()
            sys.exit(1)


    fave = connect_to_fave(
        FAVE_DEFAULT_UNIX
    ) if use_unix else connect_to_fave(
        FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
    )

    dump = {
        'type':'dump',
        'dir':odir,
        'fave':use_fave,
        'flows':use_flows,
        'network':use_network,
        'pipes':use_pipes,
        'trees':use_trees,
        'simple':keep_simple
    }

    if any([use_fave, use_flows, use_network, use_pipes, use_trees]):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)
        os.system("rm -f %s/.lock" % odir)

    lock = PersistentFileLock("%s/.lock" % odir, timeout=-1)
    lock.acquire()

    fave_sendmsg(fave, json.dumps(dump))
    fave.close()


if __name__ == '__main__':
    main(sys.argv[1:])
