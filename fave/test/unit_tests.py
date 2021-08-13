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

""" This module groups all unit tests for FaVe modules.
"""

import sys
import unittest

from test.test_utils import TestCollectionsUtilDict, TestCollectionsUtilList
from test.test_utils import TestMatchUtil, TestPacketUtil, TestPathUtil, TestJsonUtil
from test.test_netplumber import TestMapping, TestVector, TestHeaderSpace, TestModel
from test.test_topology import TestLinksModel, TestTopologyCommand
from test.test_models import TestGenericModel, TestRouterModel
from test.test_packet_filter import TestPacketFilterModel, TestPacketFilterGenerator
from test.test_models import TestSwitchModel
from test.test_tree import TestTree
from test.test_rules import TestRuleField, TestMatch, TestRule
from test.test_rules import TestForward, TestRewrite, TestMiss
from test.test_iptables_parser import TestParser
from test.test_checker import TestChecker

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
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPacketFilterGenerator)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestSwitchModel)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTree)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRuleField)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRule)
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
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRule)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestParser)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestChecker)
    )

    ret = not unittest.TextTestRunner(verbosity=2).run(SUITE).wasSuccessful()
    sys.exit(ret)
