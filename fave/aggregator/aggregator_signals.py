#!/usr/bin/env python2

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
