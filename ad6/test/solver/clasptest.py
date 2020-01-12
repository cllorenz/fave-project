import unittest
import lxml.etree as et
from src.solver.clasp import ClaspAdapter


class ClaspAdapterTest(unittest.TestCase):
    def setUp(self):
        self._input = et.parse('./test/solver/testMiniSAT.xml').getroot()
        self._ifile = './test/solver/solver.in'
        self._solver = ClaspAdapter(IFile=self._ifile)


    def tearDown(self):
        del self._input
        del self._ifile
        del self._solver


    def testSolve(self):
        result = self._solver.Solve(self._input)

        ifile = open(self._ifile,'r').read()
        expected = open('./test/solver/resultMiniSATSolve.in','r').read()
        self.assertEqual(ifile,expected)

        expected = [
            [{
                'foo' : True,
                'bar' : True,
                'baz' : False
            }],
            [{
                'foo' : True,
                'bar' : True,
                'baz' : True
            }],
            [{
                'foo' : True,
                'bar' : False,
                'baz' : False
            }]]

        self.assertIn(result, expected)


def main():
    unittest.main()


if __name__ == '__main__':
    main()
