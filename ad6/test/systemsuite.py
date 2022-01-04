import unittest
from unittest import TestSuite

import sys
import os


from system.systemtest import SystemTest

class SystemSuite(TestSuite):
    def addTests(self):
        tests = [
            'testReach',
            'testCycle',
            'testShadow',
            'testCross'
        ]
        self._suite.addTests(map(SystemTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = SystemSuite()
    suite.run()
