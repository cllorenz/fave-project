import unittest
import lxml.etree as et
from src.solver.pycosat import PycoSATAdapter


class PycoSATAdapterTest(unittest.TestCase):
    def setUp(self):
        self._input = et.parse('./test/solver/testMiniSAT.xml').getroot()
        self._solver = PycoSATAdapter()


    def tearDown(self):
        del self._solver


    def testSolve(self):
        result = self._solver.Solve(self._input)

        expected = [{
            'foo' : True,
            'bar' : False,
            'baz' : False
        }]

        self.assertEqual(result, expected)


def main():
    unittest.main()


if __name__ == '__main__':
    main()
