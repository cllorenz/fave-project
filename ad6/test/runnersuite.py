import unittest
from unittest import TestSuite

import sys
import os


from runner.runnertest import RunnerTest

class RunnerSuite(TestSuite):
    def addTests(self):
        tests = [
            'testSuitesRunReturnTheirResult',

            'testAllSuitesSucceedingIsASuccess',
            'testOneFailingSuiteFailsTheWholeRun',
            'testEverySuiteRunsEvenAfterAnEarlierFailure',
            'testSuiteReturningNoResultIsAFailure',
            'testNoSuitesIsNotAFailure'
        ]
        self._suite.addTests(map(RunnerTest,tests))


    def run(self):
        return self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = RunnerSuite()
    suite.run()
