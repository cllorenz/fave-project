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

""" This script sends a stopping event to FaVe.
"""

import sys
import json
import getopt

from util.aggregator_utils import connect_to_fave, fave_sendmsg
from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
from util.print_util import eprint

_ADDR = FAVE_DEFAULT_IP
_PORT = FAVE_DEFAULT_PORT
_UNIX = FAVE_DEFAULT_UNIX

USE_UNIX = False

try:
    ARGV = sys.argv[1:]
    OPTS, _ARGS = getopt.getopt(ARGV, "s:p:u")
except getopt.GetoptError:
    eprint("could not parse options: %s" % ARGV)
    sys.exit(1)

for opt, arg in OPTS:
    if opt == '-s':
        _ADDR = arg
    elif opt == '-p':
        _PORT = int(arg)
    elif opt == '-u':
        USE_UNIX = True

_AGGR = connect_to_fave(_UNIX) if USE_UNIX else connect_to_fave(_ADDR, _PORT)

_STOP = {
    'type':'stop'
}

fave_sendmsg(_AGGR, json.dumps(_STOP))
_AGGR.close()
