#!/usr/bin/env python2

""" This module provides printing utilities.
"""

from __future__ import print_function
import sys

def eprint(*args, **kwargs):
    """ Prints parametrizably to stderr as in Python3

    Keyword arguments:
    args -- string arguments
    kwargs -- keywords to customize string output
    """
    print(*args, file=sys.stderr, **kwargs)
