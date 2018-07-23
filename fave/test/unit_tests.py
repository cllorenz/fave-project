#!/usr/bin/env python2

import unittest

from test_utils import TestCollectionsUtilDict, TestCollectionsUtilList
from test_utils import TestMatchUtil, TestPacketUtil, TestPathUtil, TestJsonUtil
from test_netplumber import TestMapping,TestVector,TestHeaderSpace,TestModel
from test_topology import TestLinksModel,TestTopologyCommand
from test_tree import TestTree

if __name__ == '__main__':
    suite = unittest.TestSuite()

    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCollectionsUtilDict)
    )
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCollectionsUtilList)
    )
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMatchUtil)
    )
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPacketUtil)
    )
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPathUtil)
    )
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestJsonUtil)
    )

    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMapping)
    )
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestVector))
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestHeaderSpace)
    )
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestModel))

    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestLinksModel)
    )

    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTopologyCommand)
    )

    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTree)
    )

    unittest.TextTestRunner(verbosity=2).run(suite)
