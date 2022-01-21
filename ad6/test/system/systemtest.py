import unittest
import lxml.etree as et
from lxml import objectify
from src.core.instantiator import *
from src.solver.clasp import ClaspAdapter
from src.sat.satutils import SATUtils as sat
from src.xml.xmlutils import XMLUtils

class SystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examinee = et.parse('./test/system/testSystem.xml').getroot()
        XMLUtils.deannotate(cls.examinee)
        cls.solver = ClaspAdapter()
        cls.instances = Instantiator.Instantiate(cls.examinee, Reach=True, Cycle=True, Shadow=True, Cross=True)


    def setUp(self):
        self.expectation = []


    def testReach(self):
        result = self.solver.Solve(self.instances['dmz_gateway_fw0_input_r4096_reach'])
        self.assertEqual(result,self.expectation)


    def testCycle(self):
        result = self.solver.Solve(self.instances['cycle'])
        self.assertEqual(result,self.expectation)


    def testShadow(self):
        result = self.solver.Solve(self.instances['dmz_gateway_fw0_input_r4096_shadow'])
        self.assertEqual(result,self.expectation)


    def testCross(self):
        return # TODO: fix routing
        result = self.solver.Solve(self.instances['cross'])
        self.assertEqual(result,self.expectation)

def main():
    unittest.main()


if __name__ == '__main__':
    main()
