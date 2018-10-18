#!/usr/bin/env python2

""" This module groups all unit tests for FaVe modules.
"""

import unittest

from test.test_utils import TestCollectionsUtilDict, TestCollectionsUtilList
from test.test_utils import TestMatchUtil, TestPacketUtil, TestPathUtil, TestJsonUtil
from test.test_netplumber import TestMapping, TestVector, TestHeaderSpace, TestModel
from test.test_topology import TestLinksModel, TestTopologyCommand
from test.test_models import TestRouterModel
from test.test_tree import TestTree

if __name__ == '__main__':
    SUITE = unittest.TestSuite()

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCollectionsUtilDict)
    )
    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCollectionsUtilList)
    )
    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMatchUtil)
    )
    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPacketUtil)
    )
    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPathUtil)
    )
    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestJsonUtil)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMapping)
    )
    SUITE.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestVector))
    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestHeaderSpace)
    )
    SUITE.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestModel))

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestLinksModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTopologyCommand)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRouterModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTree)
    )

    unittest.TextTestRunner(verbosity=2).run(SUITE)
