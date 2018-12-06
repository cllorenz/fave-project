#!/usr/bin/env python2

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
