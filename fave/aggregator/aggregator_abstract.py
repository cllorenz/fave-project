#!/usr/bin/env python2

""" This module provides an abstract class for FaVe.
"""

import logging

class AbstractAggregator(object):
    """ This abstract class provides class members for buffer sizes and a logger.
    """

    BUF_SIZE = 4096
    LOGGER = logging.getLogger('Aggregator')
