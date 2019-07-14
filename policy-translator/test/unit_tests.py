#!/usr/bin/env python2

""" This module groups all unit tests for PolicyTranslator modules.
"""

import unittest

from test.test_policy import TestPolicy, TestRole, TestSuperrole, TestService
from test.test_policy import TestReachabilityPolicy
from test.test_policy_builder import TestPolicyBuilder

if __name__ == '__main__':
    SUITE = unittest.TestSuite()

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPolicy)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestRole)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestSuperrole)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestService)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestReachabilityPolicy)
    )

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPolicyBuilder)
    )

    unittest.TextTestRunner(verbosity=2).run(SUITE)
