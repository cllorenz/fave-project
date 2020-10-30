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

""" This module provides methods for profiling FaVe.
"""

import cProfile
from threading import Thread

PROFILE = cProfile.Profile()

def profile_method(method):
    """ Wraps a profiler around a method.

    Keyword arguments:
    method -- a method to be profiled
    """
    def profile_wrapper(*args, **kwargs):
        """ Collects profiling information while executing a method.
        """
        PROFILE.enable()
        method(*args, **kwargs)
        PROFILE.disable()
    return profile_wrapper


def dump_stats():
    """ Dumps collected profiling stats to the file \"./aggregator.stats\".
    """
    PROFILE.dump_stats("aggregator.stats")


class ProfiledThread(Thread):
    """ A thread which profiles its run method.
    """

    def run(self):
        """ A profiled version of the run method.
            Dumps stats to the file \"aggr_handler.profile\".
        """

        profiler = cProfile.Profile()
        try:
            return profiler.runcall(Thread.run, self)
            #profiler.print_stats()
        finally:
            profiler.dump_stats('aggr_handler.profile')
