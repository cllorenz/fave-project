import unittest
from unittest import TestSuite

import sys
import os


from core.initconstraintstest import InitConstraintsTest

class InitConstraintsSuite(TestSuite):
    def addTests(self):
        tests = [
            'testTwo',
            'testThree',
            'testFour',
            'testSix',
            'testSeventeen'
        ]
        self._suite.addTests(map(InitConstraintsTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = InitConstraintsSuite()
    suite.run()
