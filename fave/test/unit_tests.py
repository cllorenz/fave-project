#!/usr/bin/env python2

""" This module groups all unit tests for FaVe modules.
"""

import unittest

from test.test_utils import TestCollectionsUtilDict, TestCollectionsUtilList
from test.test_utils import TestMatchUtil, TestPacketUtil, TestPathUtil, TestJsonUtil
from test.test_netplumber import TestMapping, TestVector, TestHeaderSpace, TestModel
from test.test_topology import TestLinksModel, TestTopologyCommand
from test.test_models import TestGenericModel, TestRouterModel, TestPacketFilterModel
from test.test_models import TestSwitchModel
from test.test_tree import TestTree
from test.test_switch_rules import TestSwitchRuleField, TestMatch, TestSwitchRule
from test.test_switch_rules import TestForward, TestRewrite, TestMiss

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
        unittest.defaultTestLoader.loadTestsFromTestCase(TestGenericModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRouterModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPacketFilterModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestSwitchModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTree)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestSwitchRuleField)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestSwitchRule)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestForward)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRewrite)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMiss)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestMatch)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestSwitchRule)
    )

    unittest.TextTestRunner(verbosity=2).run(SUITE)
