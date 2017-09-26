#!/usr/bin/env python2

import unittest

from test_utils import TestCollectionsUtilDict, TestCollectionsUtilList
from test_utils import TestMatchUtil, TestPacketUtil, TestPathUtil
from test_netplumber import TestMapping,TestVector,TestHeaderSpace,TestModel


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
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMapping)
    )
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestVector))
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestHeaderSpace)
    )
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestModel))

    unittest.TextTestRunner(verbosity=2).run(suite)
