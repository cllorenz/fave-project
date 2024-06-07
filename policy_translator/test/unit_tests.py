#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2019 Claas Lorenz
# List of co-authors:
#    Benjamin Plewka <plewka@uni-potsdam.de>

# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

""" This module groups all unit tests for PolicyTranslator modules.
"""

import unittest

from test.test_policy import TestPolicy, TestRole, TestSuperrole, TestService
from test.test_policy import TestReachabilityPolicy
from test.test_policy_builder import TestPolicyBuilder
from test.test_to_iptables import TestToIptables

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

    SUITE.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestToIptables)
    )

    unittest.TextTestRunner(verbosity=2).run(SUITE)
