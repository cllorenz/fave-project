import unittest
import lxml.etree as et
from src.solver.minisat import MiniSATAdapter


class MiniSATAdapterTest(unittest.TestCase):
    def setUp(self):
        self._input = et.parse('./test/solver/testMiniSAT.xml').getroot()
        self._ifile = './test/solver/solver.in'
        self._ofile = './test/solver/solver.out'
        self._solver = MiniSATAdapter(IFile=self._ifile, OFile=self._ofile)


    def tearDown(self):
        del self._input
        del self._ifile
        del self._ofile
        del self._solver


    def testSolve(self):
        self._solver.Solve(self._input)

        ifile = open(self._ifile,'r').read()
        expected = open('./test/solver/resultMiniSATSolve.in','r').read()
        self.assertEqual(ifile,expected)

        ofile = open(self._ofile,'r').read()
        expected = open('./test/solver/resultMiniSATSolve.out','r').read()
        self.assertEqual(ofile,expected)



def main():
    unittest.main()


if __name__ == '__main__':
    main()
