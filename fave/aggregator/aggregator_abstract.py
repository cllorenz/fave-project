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

""" This module provides an abstract class for FaVe.
"""

import logging

from typing import Any, cast

TRACE = 9
if not hasattr(logging.Logger, 'trace'):
    logging.addLevelName(TRACE, "trace")
    def trace(self: logging.Logger, message: Any, *args: Any, **kws: Any) -> None:
        """ Logging function for tracing.
        """
        if self.isEnabledFor(TRACE):
            self._log(TRACE, message, args, **kws)
    logging.Logger.trace = trace  # type: ignore[attr-defined]


class TraceLogger(logging.Logger):
    """ A logging.Logger that also exposes the trace() level patched in above.
        Used only as an annotation/cast target -- loggers are still created via
        logging.getLogger() and carry trace() at runtime.
    """
    def trace(self, message: object, *args: Any, **kws: Any) -> None: ...


class AbstractAggregator(object):
    """ This abstract class provides class members for buffer sizes and a logger.
    """

    BUF_SIZE = 4096
    LOGGER: TraceLogger = cast(TraceLogger, logging.getLogger('Aggregator'))
