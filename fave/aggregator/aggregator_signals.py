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

""" This module offers signal handling for FaVe.
"""

import signal

from aggregator_singleton import AGGREGATOR

def handle_sigterm(_signum, _frame):
    """ Handler for SIGTERM signals.
    """
    if AGGREGATOR:
        AGGREGATOR.stop_aggr()


def handle_sigint(signum, frame):
    """ Handler for SIGINT signals.
    """
    handle_sigterm(signum, frame)


def register_signals():
    """ Registers SIGTERM and SIGINT handlers.
    """

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigint)
