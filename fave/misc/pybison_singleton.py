""" This module provides a constant to a global PyBison parser.
"""

PARSER = None

if PARSER is None:
    from misc.pybison_test import IP6TablesParser
    PARSER = IP6TablesParser()
