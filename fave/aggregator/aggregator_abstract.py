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

""" This module provides an abstract class for FaVe.
"""

import logging

TRACE = 9
if not hasattr(logging.Logger, 'trace'):
    logging.addLevelName(TRACE, "trace")
    def trace(self, message, *args, **kws):
        if self.isEnabledFor(TRACE):
            self._log(TRACE, message, args, **kws)
    logging.Logger.trace = trace

class AbstractAggregator(object):
    """ This abstract class provides class members for buffer sizes and a logger.
    """

    BUF_SIZE = 4096
    LOGGER = logging.getLogger('Aggregator')
