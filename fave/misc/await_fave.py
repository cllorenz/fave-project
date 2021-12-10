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
import argparse

from filelock import SoftFileLock

def main(argv):
    """ Main method.
    """

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-d', '--dump',
        dest='dump',
        default='np_dump'
    )

    args = parser.parse_args(argv)

    with SoftFileLock("%s/.lock" % args.dump, timeout=-1):
        pass

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
