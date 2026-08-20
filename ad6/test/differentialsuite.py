import unittest
from unittest import TestSuite

import sys
import os


from differential.tumdifftest import TumDifferentialTest

class DifferentialSuite(TestSuite):
    def addTests(self):
        tests = [
            'testForwardAcceptReachability'
        ]
        self._suite.addTests(map(TumDifferentialTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = DifferentialSuite()
    suite.run()
