import unittest
from unittest import TestSuite

import sys
import os


from sat.satutilstest import SATUtilsTest

class SATSuite(TestSuite):
    def addTests(self):
        tests = [
            'testReduceImplication',
            'testReduceEquality',
            'testReduceToDNC',

            'testFlattenConjunction',
            'testFlattenDisjunction',
            'testFlattenAll',

            'testConvertBinaryFormSimple',
            'testConvertBinaryFormComplex',

            'testNegationConstant',
            'testNegationVariable',
            'testNegationNegation',
            'testNegationConjunction',
            'testNegationDisjunction',
            'testNegationAll',

            'testConvertDNCToCNFNoNoclause',
            'testConvertDNCToCNFNegation',
            'testConvertDNCToCNFConjunction',
            'testConvertDNCToCNFDisjunction',
            'testConvertDNCToCNFAll',

            'testConvertToCNFEquality',
            'testConvertToCNFComplex',
            'testConvertToCNFAll'
        ]
        self._suite.addTests(map(SATUtilsTest,tests))


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = SATSuite()
    suite.run()
