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

import json

from util.aggregator_utils import UDS_ADDR, connect_to_fave, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT

_AGGR = connect_to_fave(FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT)

_STOP = {
    'type':'stop'
}

_AGGR.sendall(json.dumps(_STOP))
_AGGR.close()
