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
import argparse

from util.aggregator_utils import connect_to_fave, fave_sendmsg
from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
from util.print_util import eprint

_PARSER = argparse.ArgumentParser()
_PARSER.add_argument(
    '-s', '--server',
    dest='server',
    default=FAVE_DEFAULT_IP
)
_PARSER.add_argument(
    '-p', '--port',
    dest='port',
    type=int,
    default=FAVE_DEFAULT_PORT
)
_PARSER.add_argument(
    '-u', '--use-unix',
    dest='use_unix',
    action='store_const',
    const=True,
    default=False
)

_ARGS = _PARSER.parse_args(sys.argv[1:])

_AGGR = connect_to_fave(
    FAVE_DEFAULT_UNIX
) if _ARGS.use_unix else connect_to_fave(
    _ARGS.server, _ARGS.port
)

_STOP = {
    'type':'stop'
}

fave_sendmsg(_AGGR, json.dumps(_STOP))
_AGGR.close()
