import unittest
from unittest import TestSuite

import sys
import os


from sat.qbfutilstest import QBFUtilsTest

class QBFSuite(TestSuite):
    def addTests(self):
        tests = [
            'testMarkUnbound',
            'testUnifyVariables',
            'testConvertToPrenexConjunction',
            'testConvertToPrenexNegationExists',
            'testConvertToPrenexNegationForall',
            'testConvertToPrenexImplicationFirst',
            'testConvertToPrenexImplicationSecond',
            'testConvertToPrenexImplicationBoth',
            'testConvertToPrenexEqualityFirstExists',
            'testConvertToPrenexEqualitySecondExists',
            'testConvertToPrenexEqualityFirstForall',
            'testConvertToPrenexEqualitySecondForall',
            'testConvertToPrenexEqualityBoth',
            'testConvertQBFToPrenex'
            #'testConvertPrenexToSkolem'
        ]
        self._suite.addTests(map(QBFUtilsTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = QBFSuite()
    suite.run()
