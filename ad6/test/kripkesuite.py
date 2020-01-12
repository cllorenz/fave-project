import unittest
from unittest import TestSuite

import sys
import os


from core.kripketest import KripkeTest

class KripkeSuite(TestSuite):
    def addTests(self):
        tests = [
            'testKripke'
        ]
        self._suite.addTests(map(KripkeTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = KripkeSuite()
    suite.run()
