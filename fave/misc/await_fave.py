#/usr/bin/env python2

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
