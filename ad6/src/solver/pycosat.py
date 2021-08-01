import pycosat

from src.solver.solver import AbstractSolver
from src.xml.xmlutils import XMLUtils

class PycoSATAdapter(AbstractSolver):
    def _Prepare(self,CNF):
        self._Variables, self._DIMACS = self._ConvertToDIMACS(CNF)


    def _ReadResult(self):
        Results = []
        Result = {}

        if self._Result == []:
            return self._Result
        for Var in self._Result:
            Flag = not Var < 0
            if self._Filter(self._Variables[abs(Var)-1]):
                Result[self._Variables[abs(Var)-1]] = Flag
        Results.append(Result)

        return Results


    def _RunSolver(self):
        result = pycosat.solve(self._DIMACS)
        if result == 'UNSAT':
            self._Result = []
        else:
            self._Result = result

    def Reset(self):
        self._DIMACS = []
        self._Result = []
        self._Variables = []

    def __init__(self):
        self._DIMACS = []
        self._Result = []
        self._Variables = []
