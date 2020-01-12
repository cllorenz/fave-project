import unittest
from unittest import TestSuite

import sys
import os


from test.xml.xmlutilstest import XMLUtilsTest
from test.xml.translatortest import TranslatorTest

class XMLSuite(TestSuite):
    def addTests(self):
        tests = [
            'testIp4',
            'testIp6',
            'testCIDR',
            'testPort',
            'testIf'
        ]
        self._suite.addTests(map(XMLUtilsTest,tests))
        tests = [
            'testXMLToJSON',
            'testJSONToXML',
            'testTranslate'
        ]
        self._suite.addTests(map(TranslatorTest,tests))

    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = SolverSuite()
    suite.run()
