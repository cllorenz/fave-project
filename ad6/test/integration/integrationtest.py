import unittest
import lxml.etree as et
from lxml import objectify
from src.core.instantiator import *
from src.solver.clasp import ClaspAdapter
from src.solver.minisat import MiniSATAdapter
from src.sat.satutils import SATUtils as sat
from src.xml.xmlutils import XMLUtils

class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examinee = et.parse('./test/integration/testIntegration.xml').getroot()
        cls.solver = MiniSATAdapter()
        XMLUtils.deannotate(cls.examinee)
        cls.instances = Instantiator.Instantiate(cls.examinee, Reach=True, Cycle=True, Shadow=True, Cross=True)


    def setUp(self):
        self.expectation = []


    def testReach(self):
        result = self.solver.Solve(self.instances['net0_n1_eth0_out_reach'])
        self.assertEqual(result,self.expectation)


    def testCycle(self):
        result = self.solver.Solve(self.instances['cycle'])
        self.assertEqual(result,self.expectation)


    def testShadow(self):
        result = self.solver.Solve(self.instances['net0_n1_eth0_out_shadow'])
        self.assertEqual(result,self.expectation)


    def testCross(self):
        result = self.solver.Solve(self.instances['cross'])
        self.assertEqual(result,self.expectation)

def main():
    unittest.main()


if __name__ == '__main__':
    main()
