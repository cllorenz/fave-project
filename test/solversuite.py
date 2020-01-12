import unittest
from unittest import TestSuite

import sys
import os


from solver.minisattest import MiniSATAdapterTest
from solver.clasptest import ClaspAdapterTest
from solver.pycosattest import PycoSATAdapterTest

class SolverSuite(TestSuite):
    def addTests(self):
        tests = [
            'testSolve'
        ]
        self._suite.addTests(map(MiniSATAdapterTest,tests))
        self._suite.addTests(map(ClaspAdapterTest,tests))
        self._suite.addTests(map(PycoSATAdapterTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = SolverSuite()
    suite.run()
